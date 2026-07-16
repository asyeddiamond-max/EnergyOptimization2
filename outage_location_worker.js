/*
 * Web Worker orchestration for outage_location_model.js.
 *
 * Protocol: connecticut_outage_worker_v1 / version 1.
 * The Worker owns validation, progress, cancellation boundaries, timings, and
 * structured-clone transport. All scientific calculations remain in the model.
 */
(function startOutageLocationWorker() {
  "use strict";

  const PROTOCOL = "connecticut_outage_worker_v1";
  const VERSION = 1;
  const CANCELLED = Symbol("cancelled");
  let model;
  let send;
  let subscribe;
  let yieldToMessages;

  if (typeof importScripts === "function" && typeof self !== "undefined") {
    importScripts("outage_location_model.js");
    model = self.OutageLocationModel;
    send = (message, transfer = []) => self.postMessage(message, transfer);
    subscribe = (handler) => self.addEventListener("message", (event) => handler(event.data));
    yieldToMessages = () => new Promise((resolve) => setTimeout(resolve, 0));
  } else if (typeof require === "function") {
    const { parentPort } = require("node:worker_threads");
    model = require("./outage_location_model.js");
    if (!parentPort) throw new Error("outage_location_worker.js must run inside a Worker");
    send = (message, transfer = []) => parentPort.postMessage(message, transfer);
    subscribe = (handler) => parentPort.on("message", handler);
    yieldToMessages = () => new Promise((resolve) => setImmediate(resolve));
  } else {
    throw new Error("No supported Worker messaging environment is available");
  }

  let latestRunId = null;
  const activeRuns = new Set();
  const cancelledRuns = new Set();
  const cancellationMessagesSent = new Set();

  function envelope(type, runId, fields = {}) {
    return { protocol: PROTOCOL, version: VERSION, type, runId, ...fields };
  }

  function validRunId(runId) {
    return (typeof runId === "string" && runId.length > 0)
      || (typeof runId === "number" && Number.isFinite(runId));
  }

  function validateMessage(message) {
    if (!message || typeof message !== "object" || Array.isArray(message)) {
      throw new model.InputValidationError("Worker message must be an object");
    }
    if (message.protocol !== PROTOCOL || message.version !== VERSION) {
      throw new model.InputValidationError(`Worker protocol must be ${PROTOCOL} version ${VERSION}`);
    }
    if (!validRunId(message.runId)) {
      throw new model.InputValidationError("Worker runId must be a non-empty string or finite number");
    }
    if (message.type !== "generate" && message.type !== "cancel" && message.type !== "status") {
      throw new model.InputValidationError("Worker message type must be generate, cancel, or status");
    }
    if (message.type === "generate" && (!message.input || typeof message.input !== "object")) {
      throw new model.InputValidationError("Generate message must include an input object");
    }
  }

  function postProgress(runId, stage, progress, message, timingsMs) {
    send(envelope("progress", runId, {
      stage,
      progress,
      message,
      timingsMs: { ...timingsMs },
    }));
  }

  function cancelReason(runId) {
    return cancelledRuns.has(runId) ? "cancelled" : "superseded";
  }

  function postCancelledOnce(runId, stage) {
    if (cancellationMessagesSent.has(runId)) return;
    cancellationMessagesSent.add(runId);
    send(envelope("cancelled", runId, { stage, reason: cancelReason(runId) }));
  }

  function ensureCurrent(runId, stage) {
    if (cancelledRuns.has(runId) || latestRunId !== runId) {
      postCancelledOnce(runId, stage);
      throw CANCELLED;
    }
  }

  async function stage(runId, timingsMs, name, progress, message, operation) {
    ensureCurrent(runId, name);
    postProgress(runId, name, progress, message, timingsMs);
    await yieldToMessages();
    ensureCurrent(runId, name);
    const started = performance.now();
    const value = operation();
    timingsMs[name] = performance.now() - started;
    await yieldToMessages();
    ensureCurrent(runId, name);
    return value;
  }

  function flattenGrid(grid, Type = Float64Array) {
    const rows = grid.length;
    const columns = grid[0].length;
    const values = new Type(rows * columns);
    let offset = 0;
    for (let row = 0; row < rows; row += 1) {
      for (let column = 0; column < columns; column += 1) {
        values[offset] = grid[row][column];
        offset += 1;
      }
    }
    return values;
  }

  function prepareSurfaceTransport(customer, weather, impact) {
    const surfaces = {
      rows: customer.latitudes.length,
      columns: customer.longitudes.length,
      latitudes: Float64Array.from(customer.latitudes),
      longitudes: Float64Array.from(customer.longitudes),
      mask: flattenGrid(customer.connecticutMask, Uint8Array),
      customerExposure: flattenGrid(customer.smoothedCustomerAccounts),
      weatherSeverity: flattenGrid(weather.weatherSeverity),
      rawImpact: flattenGrid(impact.rawImpact),
      smoothedImpact: flattenGrid(impact.smoothedImpact),
      probability: flattenGrid(impact.samplingProbability),
    };
    const transfer = [
      surfaces.latitudes.buffer,
      surfaces.longitudes.buffer,
      surfaces.mask.buffer,
      surfaces.customerExposure.buffer,
      surfaces.weatherSeverity.buffer,
      surfaces.rawImpact.buffer,
      surfaces.smoothedImpact.buffer,
      surfaces.probability.buffer,
    ];
    return { surfaces, transfer };
  }

  function prepareTimelineSurfaceTransport(customer, timeline) {
    const surfaces = {
      mode: "timeline",
      rows: customer.latitudes.length,
      columns: customer.longitudes.length,
      latitudes: Float64Array.from(customer.latitudes),
      longitudes: Float64Array.from(customer.longitudes),
      mask: flattenGrid(customer.connecticutMask, Uint8Array),
      customerExposure: flattenGrid(customer.smoothedCustomerAccounts, Float32Array),
      timeline: {
        stormId: timeline.stormId,
        stormName: timeline.stormName,
        startTime: timeline.startTime,
        endTime: timeline.endTime,
        intervalMinutes: timeline.intervalMinutes,
        antecedentRainHours: timeline.antecedentRainHours,
        rainInputKind: timeline.rainInputKind,
        frames: timeline.frames.map((frame) => ({
          frameIndex: frame.frameIndex,
          validTime: frame.validTime,
          windGustMph: flattenGrid(frame.weather.windMph, Float32Array),
          rain1hIn: flattenGrid(frame.rain1hIn, Float32Array),
          rain6hIn: flattenGrid(frame.rain6hIn, Float32Array),
          weatherSeverity: flattenGrid(frame.weather.weatherSeverity, Float32Array),
          rawImpact: flattenGrid(frame.impact.rawImpact, Float32Array),
          smoothedImpact: flattenGrid(frame.impact.smoothedImpact, Float32Array),
        })),
      },
    };
    const transfer = [
      surfaces.latitudes.buffer,
      surfaces.longitudes.buffer,
      surfaces.mask.buffer,
      surfaces.customerExposure.buffer,
    ];
    for (const frame of surfaces.timeline.frames) {
      transfer.push(
        frame.windGustMph.buffer,
        frame.rain1hIn.buffer,
        frame.rain6hIn.buffer,
        frame.weatherSeverity.buffer,
        frame.rawImpact.buffer,
        frame.smoothedImpact.buffer,
      );
    }
    return { surfaces, transfer };
  }

  function buildSummary(segments, scenario, customer, weather, impact, timingsMs) {
    const feederCandidateSegments = segments.reduce(
      (count, segment) => count + (segment.networkKind === "feeder" ? 1 : 0), 0,
    );
    const feederOutages = scenario.outages.reduce(
      (count, outage) => count + (outage.is_feeder === 1 ? 1 : 0), 0,
    );
    const totalSegmentWeight = segments.reduce((sum, segment) => sum + segment.weight, 0);
    return {
      candidateSegments: segments.length,
      feederCandidateSegments,
      lateralCandidateSegments: segments.length - feederCandidateSegments,
      sampledOutages: scenario.outages.length,
      uniqueSampledSegments: new Set(scenario.outages.map((outage) => outage.networkSegmentId)).size,
      feederOutages,
      lateralOutages: scenario.outages.length - feederOutages,
      representedCustomers: scenario.totalCustomers,
      totalSegmentWeight,
      feederSamplingWeightShare: segments.reduce(
        (sum, segment) => sum + (segment.networkKind === "feeder" ? segment.weight : 0), 0,
      ) / totalSegmentWeight,
      surface: {
        validConnecticutCells: customer.summary.validCellCount,
        totalCustomerAccounts: customer.totalCustomerAccounts,
        positiveWeatherCells: weather.summary.positiveSeverityCells,
        maximumWeatherSeverity: weather.summary.maximumSeverity,
        rawImpactTotal: impact.summary.rawTotal,
        smoothedImpactTotal: impact.summary.smoothedTotal,
        rawImpactPositiveCells: impact.summary.rawPositiveCells,
        smoothedImpactPositiveCells: impact.summary.smoothedPositiveCells,
      },
      timingsMs: { ...timingsMs },
    };
  }

  async function generateBasic(runId, input, timingsMs, runStarted) {
    let currentStage = "validation";
    try {
      const config = await stage(
        runId, timingsMs, currentStage, 0.05, "Validating basic placement inputs…",
        () => model.validateConfig(input.config),
      );
      currentStage = "network-weighting";
      const segments = await stage(
        runId, timingsMs, currentStage, 0.36, "Weighting network segments by length…",
        () => model.buildBasicNetworkSegments(input.network, config),
      );
      currentStage = "sampling";
      const scenario = await stage(
        runId, timingsMs, currentStage, 0.82, "Sampling unique basic outage locations…",
        () => model.sampleOutageScenario(segments, config, input.inputs || {}, input.boundary || null),
      );
      currentStage = "serialization";
      postProgress(runId, currentStage, 0.96, "Preparing basic-placement result…", timingsMs);
      await yieldToMessages();
      ensureCurrent(runId, currentStage);
      const feederCandidateSegments = segments.filter((segment) => segment.networkKind === "feeder").length;
      const feederOutages = scenario.outages.filter((outage) => outage.is_feeder === 1).length;
      const totalSegmentWeight = segments.reduce((sum, segment) => sum + segment.weight, 0);
      const summary = {
        placementModel: "basic_network_v1",
        candidateSegments: segments.length,
        feederCandidateSegments,
        lateralCandidateSegments: segments.length - feederCandidateSegments,
        sampledOutages: scenario.outages.length,
        uniqueSampledSegments: new Set(scenario.outages.map((outage) => outage.networkSegmentId)).size,
        feederOutages,
        lateralOutages: scenario.outages.length - feederOutages,
        representedCustomers: scenario.totalCustomers,
        totalSegmentWeight,
        surface: null,
        timingsMs: { ...timingsMs },
        calculationRuntimeMs: Object.values(timingsMs).reduce((sum, value) => sum + value, 0),
        totalRuntimeMs: performance.now() - runStarted,
      };
      postProgress(runId, "complete", 1, "Basic outage locations generated.", timingsMs);
      send(envelope("result", runId, {
        result: { ...scenario, surfaces: null, summary },
      }));
      return true;
    } catch (error) {
      if (error === CANCELLED) throw error;
      error.workerStage = currentStage;
      throw error;
    }
  }

  async function generateTimeline(runId, input, timingsMs, runStarted) {
    let currentStage = "timeline-validation";
    try {
      await stage(
        runId,
        timingsMs,
        currentStage,
        0.04,
        "Validating curated storm timeline…",
        () => {
          const config = model.validateConfig(input.config);
          const timeline = model.normalizeWeatherTimeline(input.weatherTimeline ?? input.weather_timeline);
          if (config.stormId !== timeline.stormId) {
            throw new model.InputValidationError(
              `config stormId ${config.stormId} does not match timeline stormId ${timeline.stormId}`,
            );
          }
        },
      );
      currentStage = "timeline-modeling";
      const result = await stage(
        runId,
        timingsMs,
        currentStage,
        0.18,
        "Calculating 24 hourly weather, impact, and outage-risk frames…",
        () => model.generateTimelineOutageScenario(input),
      );

      currentStage = "timeline-serialization";
      postProgress(runId, currentStage, 0.94, "Preparing animated map frames…", timingsMs);
      await yieldToMessages();
      ensureCurrent(runId, currentStage);
      const started = performance.now();
      const transported = prepareTimelineSurfaceTransport(
        result.surfaces.customer,
        result.surfaces.timeline,
      );
      timingsMs[currentStage] = performance.now() - started;
      const summary = {
        ...result.summary,
        timingsMs: { ...timingsMs },
        calculationRuntimeMs: Object.values(timingsMs).reduce((sum, value) => sum + value, 0),
        totalRuntimeMs: performance.now() - runStarted,
      };
      const { surfaces: unusedSurfaces, ...scenario } = result;
      ensureCurrent(runId, currentStage);
      postProgress(runId, "complete", 1, "Timestamped outage locations generated.", timingsMs);
      send(envelope("result", runId, {
        result: {
          ...scenario,
          surfaces: transported.surfaces,
          summary,
        },
      }), transported.transfer);
      return true;
    } catch (error) {
      if (error === CANCELLED) throw error;
      error.workerStage = currentStage;
      throw error;
    }
  }

  async function generate(message) {
    const { runId, input } = message;
    const timingsMs = {};
    const runStarted = performance.now();
    let currentStage = "validation";
    activeRuns.add(runId);
    try {
      const mode = input.mode || "research";
      if (mode !== "research" && mode !== "basic" && mode !== "timeline") {
        throw new model.InputValidationError("input.mode must be research, timeline, or basic");
      }
      if (mode === "basic") {
        await generateBasic(runId, input, timingsMs, runStarted);
        return;
      }
      if (mode === "timeline") {
        await generateTimeline(runId, input, timingsMs, runStarted);
        return;
      }
      const validated = await stage(runId, timingsMs, "validation", 0.03, "Validating model inputs…", () => {
        const config = model.validateConfig(input.config);
        const weather = model.normalizeWeather(input.weather);
        if (config.stormId !== weather.stormId) {
          throw new model.InputValidationError(
            `config stormId ${config.stormId} does not match weather stormId ${weather.stormId}`,
          );
        }
        return { config, weather };
      });

      currentStage = "customer-exposure";
      const customer = await stage(
        runId, timingsMs, currentStage, 0.12, "Allocating and smoothing customer exposure…",
        () => model.buildCustomerExposureSurface(
          input.boundary,
          input.censusTracts,
          validated.weather.latitudes,
          validated.weather.longitudes,
          {
            smoothingKm: validated.config.customerSmoothingKm,
            ruralBaselineFraction: validated.config.ruralBaselineFraction,
          },
        ),
      );

      currentStage = "weather-severity";
      const weather = await stage(
        runId, timingsMs, currentStage, 0.31, "Calculating wind and rain severity…",
        () => model.buildWeatherSeveritySurface(
          input.weather, customer.connecticutMask, validated.config,
        ),
      );

      currentStage = "impact-smoothing";
      const impact = await stage(
        runId, timingsMs, currentStage, 0.45, "Combining exposure and Gaussian-smoothed impact…",
        () => model.buildCombinedImpactSurface(customer, weather, validated.config),
      );

      currentStage = "network-weighting";
      const segments = await stage(
        runId, timingsMs, currentStage, 0.58, "Weighting atomic feeder and lateral segments…",
        () => model.buildWeightedNetworkSegments(
          input.network, customer, weather, impact, validated.config,
        ),
      );

      currentStage = "sampling";
      const scenario = await stage(
        runId, timingsMs, currentStage, 0.88, "Sampling unique outage locations…",
        () => model.sampleOutageScenario(segments, validated.config, input.inputs || {}, input.boundary),
      );

      currentStage = "serialization";
      postProgress(runId, currentStage, 0.96, "Preparing map surfaces…", timingsMs);
      await yieldToMessages();
      ensureCurrent(runId, currentStage);
      const started = performance.now();
      const summary = buildSummary(segments, scenario, customer, weather, impact, timingsMs);
      const transported = prepareSurfaceTransport(customer, weather, impact);
      timingsMs[currentStage] = performance.now() - started;
      summary.timingsMs = { ...timingsMs };
      summary.calculationRuntimeMs = Object.values(timingsMs).reduce((sum, value) => sum + value, 0);
      summary.totalRuntimeMs = performance.now() - runStarted;
      ensureCurrent(runId, currentStage);
      postProgress(runId, "complete", 1, "Outage locations generated.", timingsMs);
      send(envelope("result", runId, {
        result: {
          ...scenario,
          surfaces: transported.surfaces,
          summary,
        },
      }), transported.transfer);
    } catch (error) {
      if (error !== CANCELLED) {
        send(envelope("error", runId, {
          error: {
            name: error && error.name ? error.name : "Error",
            message: error && error.message ? error.message : String(error),
            stage: error && error.workerStage ? error.workerStage : currentStage,
          },
        }));
      }
    } finally {
      activeRuns.delete(runId);
      cancelledRuns.delete(runId);
    }
  }

  function handleMessage(message) {
    try {
      validateMessage(message);
      if (message.type === "status") {
        send(envelope("ready", message.runId, { capabilities: {
          progress: true,
          cancellation: "between-stages",
          supersession: true,
          transferableSurfaces: true,
          timelineWeather: true,
        } }));
        return;
      }
      if (message.type === "cancel") {
        cancelledRuns.add(message.runId);
        if (!activeRuns.has(message.runId)) postCancelledOnce(message.runId, "not-active");
        return;
      }
      if (activeRuns.has(message.runId)) {
        throw new model.InputValidationError(`runId ${message.runId} is already active`);
      }
      latestRunId = message.runId;
      cancellationMessagesSent.delete(message.runId);
      void generate(message);
    } catch (error) {
      const runId = message && validRunId(message.runId) ? message.runId : null;
      send(envelope("error", runId, {
        error: {
          name: error && error.name ? error.name : "Error",
          message: error && error.message ? error.message : String(error),
          stage: "message-validation",
        },
      }));
    }
  }

  subscribe(handleMessage);
  send(envelope("ready", null, { capabilities: {
    progress: true,
    cancellation: "between-stages",
    supersession: true,
    transferableSurfaces: true,
    timelineWeather: true,
  } }));
})();

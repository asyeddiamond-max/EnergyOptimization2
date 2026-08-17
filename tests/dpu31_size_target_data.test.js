"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.resolve(__dirname, "..");
const VALIDATION_DIR = path.join(ROOT, "data", "validation");

function readNumericCsv(filename, expectedHeaders) {
  const text = fs.readFileSync(path.join(VALIDATION_DIR, filename), "utf8").trim();
  const [headerLine, ...lines] = text.split(/\r?\n/);
  const headers = headerLine.split(",");
  assert.deepEqual(headers, expectedHeaders, `${filename} headers`);
  return lines.map((line, rowIndex) => {
    const values = line.split(",");
    assert.equal(values.length, headers.length, `${filename} row ${rowIndex + 2}`);
    return Object.fromEntries(headers.map((header, columnIndex) => {
      const value = Number(values[columnIndex]);
      assert.ok(Number.isFinite(value), `${filename} ${header} row ${rowIndex + 2}`);
      return [header, value];
    }));
  });
}

function closeTo(actual, expected, tolerance = 1e-12) {
  assert.ok(
    Math.abs(actual - expected) <= tolerance,
    `${actual} differs from ${expected}`,
  );
}

const bins = readNumericCsv(
  "dpu31_size_target_bins.csv",
  ["lo", "hi", "jobs", "job_share", "cust_share"],
);
const quantiles = readNumericCsv(
  "dpu31_size_target_quantiles.csv",
  ["quantile", "customers"],
);

test("D.P.U. 24-41 size bins are contiguous and reconcile exactly", () => {
  assert.equal(bins.length, 13);
  assert.equal(bins[0].lo, 1);
  assert.equal(bins.at(-1).hi, 4096);

  for (let index = 0; index < bins.length; index += 1) {
    const bin = bins[index];
    assert.ok(bin.lo < bin.hi);
    assert.ok(Number.isInteger(bin.jobs) && bin.jobs > 0);
    assert.ok(bin.job_share > 0 && bin.job_share < 1);
    assert.ok(bin.cust_share > 0 && bin.cust_share < 1);
    if (index > 0) assert.equal(bin.lo, bins[index - 1].hi);
  }

  const totalJobs = bins.reduce((sum, bin) => sum + bin.jobs, 0);
  const totalJobShare = bins.reduce((sum, bin) => sum + bin.job_share, 0);
  const totalCustomerShare = bins.reduce((sum, bin) => sum + bin.cust_share, 0);
  assert.equal(totalJobs, 2377);
  closeTo(totalJobShare, 1);
  closeTo(totalCustomerShare, 1);

  for (const bin of bins) closeTo(bin.job_share, bin.jobs / totalJobs);

  // The first two half-open bins contain only sizes 1 and 2, so each one
  // independently identifies the denominator used for customer shares.
  const totalFromOneCustomerJobs = bins[0].jobs / bins[0].cust_share;
  const totalFromTwoCustomerJobs = (bins[1].jobs * 2) / bins[1].cust_share;
  closeTo(totalFromOneCustomerJobs, 306020, 1e-6);
  closeTo(totalFromTwoCustomerJobs, 306020, 1e-6);
  closeTo(totalFromOneCustomerJobs / totalJobs, 128.74211190576358, 1e-12);

  const atMostTwo = bins[0].jobs + bins[1].jobs;
  assert.equal(atMostTwo, 598);
  closeTo(atMostTwo / totalJobs, 0.25157761884728647);

  const belowSixteen = bins.slice(0, 5).reduce((sum, bin) => sum + bin.jobs, 0);
  assert.equal(belowSixteen, 1160);
  closeTo(belowSixteen / totalJobs, 0.4880100967606226);

  const atLeast512 = bins.slice(10);
  assert.equal(atLeast512.reduce((sum, bin) => sum + bin.jobs, 0), 168);
  closeTo(
    atLeast512.reduce((sum, bin) => sum + bin.cust_share, 0),
    0.6242304424547416,
  );

  const atLeast1024 = bins.slice(11);
  assert.equal(atLeast1024.reduce((sum, bin) => sum + bin.jobs, 0), 71);
  closeTo(
    atLeast1024.reduce((sum, bin) => sum + bin.cust_share, 0),
    0.3927717142670414,
  );
});

test("D.P.U. quantile checklist preserves the supplied interpolation values", () => {
  assert.deepEqual(
    quantiles.map(({ quantile }) => quantile),
    [10, 25, 50, 75, 90, 95, 99, 99.9],
  );
  assert.deepEqual(
    quantiles.map(({ customers }) => customers),
    [1, 2, 16, 80, 325, 706.1999999999998, 1779.6399999999976, 2915.0240000000254],
  );
});

test("pre-change fixed-50 generator baseline is recorded against the target bins", () => {
  const totalJobs = bins.reduce((sum, bin) => sum + bin.jobs, 0);
  const baselineCounts = bins.map((bin) =>
    50 >= bin.lo && 50 < bin.hi ? totalJobs : 0);
  assert.deepEqual(baselineCounts, [0, 0, 0, 0, 0, 0, 2377, 0, 0, 0, 0, 0, 0]);

  const baselineShares = baselineCounts.map((count) => count / totalJobs);
  const totalVariation = 0.5 * bins.reduce(
    (sum, bin, index) => sum + Math.abs(bin.job_share - baselineShares[index]),
    0,
  );
  closeTo(totalVariation, 0.8864114429953723);
  assert.equal(baselineShares[6], 1);
  closeTo(bins[6].job_share, 0.11358855700462768);
});

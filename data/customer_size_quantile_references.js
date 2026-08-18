/*
 * Customer-size quantile references used only for visual validation.
 *
 * nationalGridDpu31 reproduces data/validation/dpu31_size_target_quantiles.csv.
 * stormClasses transcribes the table supplied by Dr. Dave Wanik on 2026-08-18.
 * The supplied table did not define the small/medium/large class thresholds.
 * Its four-major-event column was reported as ranges, so those values are
 * preserved as a band rather than converted into a single curve.
 */
window.CUSTOMER_SIZE_QUANTILE_REFERENCES = Object.freeze({
  nationalGridDpu31: {
    label: "National Grid D.P.U. 24-41",
    calibrationRole: "primary customer-size target",
    points: [
      { percentile: 10, customers: 1 },
      { percentile: 25, customers: 2 },
      { percentile: 50, customers: 16 },
      { percentile: 75, customers: 80 },
      { percentile: 90, customers: 325 },
      { percentile: 95, customers: 706.1999999999998 },
      { percentile: 99, customers: 1779.6399999999976 },
      { percentile: 99.9, customers: 2915.0240000000254 },
    ],
  },
  stormClasses: {
    label: "Dave storm-size-class reference",
    receivedDate: "2026-08-18",
    smallEventCount: 562,
    mediumEventCount: 279,
    largeEventCount: 80,
    majorEventCount: 4,
    classThresholdsAvailable: false,
    calibrationRole: "secondary validation only",
    points: [
      { percentile: 10, small: 1, medium: 1, large: 1, majorLow: 1, majorHigh: 1 },
      { percentile: 20, small: 1, medium: 1, large: 1, majorLow: 1, majorHigh: 1 },
      { percentile: 25, small: 2, medium: 2, large: 1, majorLow: 1, majorHigh: 1 },
      { percentile: 30, small: 3, medium: 3, large: 2, majorLow: 1, majorHigh: 1 },
      { percentile: 40, small: 5, medium: 6, large: 4, majorLow: 1, majorHigh: 1 },
      { percentile: 50, small: 9, medium: 10, large: 7, majorLow: 2, majorHigh: 2 },
      { percentile: 60, small: 15, medium: 17, large: 14, majorLow: 5, majorHigh: 7 },
      { percentile: 70, small: 26, medium: 30, large: 28, majorLow: 13, majorHigh: 20 },
      { percentile: 75, small: 35, medium: 41, large: 39, majorLow: 20, majorHigh: 32 },
      { percentile: 80, small: 50, medium: 58, large: 55, majorLow: 34, majorHigh: 50 },
      { percentile: 90, small: 123, medium: 142, large: 138, majorLow: 105, majorHigh: 143 },
      { percentile: 95, small: 263, medium: 301, large: 319, majorLow: 255, majorHigh: 347 },
      { percentile: 97.5, small: 441, medium: 494, large: 520, majorLow: 500, majorHigh: 594 },
      { percentile: 99, small: 654, medium: 798, large: 828, majorLow: 813, majorHigh: 979 },
    ],
  },
});

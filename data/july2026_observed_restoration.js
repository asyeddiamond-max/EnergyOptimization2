// July 4, 2026 REAL observed restoration trajectory (Eversource simultaneous customers-out),
// for the main sim's restoration-curve comparison overlay. Peak-based (NOT the ~176-180k
// cumulative), date-verified from cross-referenced reporting -- see data/observed_curve.csv.
// points = [hours_since_onset, customers_out]. Peak "about 94,000" (CT Mirror / spokesman Reiss).
window.JULY4_OBSERVED = {
  peak: 94000,
  points: [[0,0],[3.5,82522],[5.0,94000],[14.0,71265],[20.9,57280],[26.0,45288],
           [27.0,40000],[44.0,21731],[75.75,700],[88.0,800]]
};

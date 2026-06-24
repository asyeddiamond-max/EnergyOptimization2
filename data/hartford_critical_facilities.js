// Hartford County critical facilities — sourced from HIFLD (Homeland Infrastructure
// Foundation-Level Data) open datasets: hospitals, fire stations, EMS stations,
// and water treatment plants. Coordinates are WGS-84.
// Sources:
//   Hospitals: https://hifld-geoplatform.opendata.arcgis.com/datasets/hospitals
//   Fire stations: https://hifld-geoplatform.opendata.arcgis.com/datasets/fire-stations
//   EMS stations: https://hifld-geoplatform.opendata.arcgis.com/datasets/emergency-medical-service-ems-stations
// Last updated: 2024 HIFLD release

window.HARTFORD_CRITICAL_FACILITIES = [
  // === HOSPITALS ===
  {name:"Hartford Hospital", type:"hospital", lat:41.7544, lon:-72.6838, town:"Hartford", beds:867},
  {name:"Connecticut Children's Medical Center", type:"hospital", lat:41.7620, lon:-72.6880, town:"Hartford", beds:187},
  {name:"Saint Francis Hospital", type:"hospital", lat:41.7806, lon:-72.6992, town:"Hartford", beds:617},
  {name:"The Hospital of Central Connecticut — New Britain", type:"hospital", lat:41.6576, lon:-72.7893, town:"New Britain", beds:414},
  {name:"UConn John Dempsey Hospital", type:"hospital", lat:41.7320, lon:-72.7920, town:"Farmington", beds:224},
  {name:"Bristol Hospital", type:"hospital", lat:41.6758, lon:-72.9436, town:"Bristol", beds:134},
  {name:"Manchester Memorial Hospital", type:"hospital", lat:41.7767, lon:-72.5290, town:"Manchester", beds:249},
  {name:"MidState Medical Center", type:"hospital", lat:41.6130, lon:-72.8661, town:"Meriden", beds:97},
  {name:"Veterans Affairs Medical Center — Newington", type:"hospital", lat:41.6878, lon:-72.7279, town:"Newington", beds:60},

  // === FIRE STATIONS ===
  {name:"Hartford Fire HQ — Pearl St", type:"fire", lat:41.7640, lon:-72.6775, town:"Hartford"},
  {name:"Hartford Fire — Engine 10 / Ladder 2", type:"fire", lat:41.7457, lon:-72.6907, town:"Hartford"},
  {name:"Hartford Fire — Engine 16 / Ladder 5", type:"fire", lat:41.7874, lon:-72.6933, town:"Hartford"},
  {name:"Hartford Fire — Engine 14", type:"fire", lat:41.7382, lon:-72.6742, town:"Hartford"},
  {name:"Hartford Fire — Engine 7", type:"fire", lat:41.7710, lon:-72.7028, town:"Hartford"},
  {name:"Hartford Fire — Engine 11", type:"fire", lat:41.7518, lon:-72.7058, town:"Hartford"},
  {name:"New Britain Fire HQ", type:"fire", lat:41.6612, lon:-72.7828, town:"New Britain"},
  {name:"New Britain Fire — Station 4", type:"fire", lat:41.6690, lon:-72.7710, town:"New Britain"},
  {name:"New Britain Fire — Station 7", type:"fire", lat:41.6538, lon:-72.8012, town:"New Britain"},
  {name:"West Hartford Fire — Station 1", type:"fire", lat:41.7618, lon:-72.7422, town:"West Hartford"},
  {name:"West Hartford Fire — Station 4", type:"fire", lat:41.7530, lon:-72.7620, town:"West Hartford"},
  {name:"West Hartford Fire — Station 5", type:"fire", lat:41.7790, lon:-72.7530, town:"West Hartford"},
  {name:"Bristol Fire HQ", type:"fire", lat:41.6718, lon:-72.9460, town:"Bristol"},
  {name:"Bristol Fire — Forestville", type:"fire", lat:41.6640, lon:-72.9118, town:"Bristol"},
  {name:"Manchester Fire — Station 1", type:"fire", lat:41.7759, lon:-72.5230, town:"Manchester"},
  {name:"Manchester Fire — Station 2", type:"fire", lat:41.7850, lon:-72.5365, town:"Manchester"},
  {name:"Enfield Fire — Station 1", type:"fire", lat:41.9762, lon:-72.5917, town:"Enfield"},
  {name:"East Hartford Fire — Station 1", type:"fire", lat:41.7630, lon:-72.6180, town:"East Hartford"},
  {name:"East Hartford Fire — Station 3", type:"fire", lat:41.7915, lon:-72.6050, town:"East Hartford"},
  {name:"Southington Fire — Station 1", type:"fire", lat:41.5965, lon:-72.8775, town:"Southington"},
  {name:"Glastonbury Fire — Station 1", type:"fire", lat:41.7126, lon:-72.6081, town:"Glastonbury"},
  {name:"South Windsor Fire — Station 1", type:"fire", lat:41.8237, lon:-72.6223, town:"South Windsor"},
  {name:"Windsor Fire — Station 1", type:"fire", lat:41.8525, lon:-72.6437, town:"Windsor"},
  {name:"Newington Fire — Station 1", type:"fire", lat:41.6981, lon:-72.7237, town:"Newington"},
  {name:"Wethersfield Fire — Station 1", type:"fire", lat:41.7142, lon:-72.6526, town:"Wethersfield"},
  {name:"Rocky Hill Fire — Station 1", type:"fire", lat:41.6648, lon:-72.6648, town:"Rocky Hill"},
  {name:"Bloomfield Fire — Station 1", type:"fire", lat:41.8281, lon:-72.7295, town:"Bloomfield"},
  {name:"Simsbury Fire — Station 1", type:"fire", lat:41.8762, lon:-72.8009, town:"Simsbury"},
  {name:"Avon Fire — Station 1", type:"fire", lat:41.8098, lon:-72.8303, town:"Avon"},
  {name:"Farmington Fire — Station 1", type:"fire", lat:41.7201, lon:-72.8320, town:"Farmington"},
  {name:"Canton Fire — Station 1", type:"fire", lat:41.8348, lon:-72.8945, town:"Canton"},
  {name:"Granby Fire — Station 1", type:"fire", lat:41.9526, lon:-72.7898, town:"Granby"},

  // === EMS / AMBULANCE ===
  {name:"American Medical Response — Hartford", type:"ems", lat:41.7580, lon:-72.6720, town:"Hartford"},
  {name:"ASM — Manchester", type:"ems", lat:41.7780, lon:-72.5260, town:"Manchester"},
  {name:"Aetna Ambulance — Hartford", type:"ems", lat:41.7690, lon:-72.6810, town:"Hartford"},

  // === WATER TREATMENT PLANTS ===
  {name:"MDC Water Treatment — West Hartford", type:"water", lat:41.7550, lon:-72.7610, town:"West Hartford"},
  {name:"MDC Reservoir #6 Pumping — Bloomfield", type:"water", lat:41.8130, lon:-72.7380, town:"Bloomfield"},
  {name:"New Britain Water — Shuttle Meadow", type:"water", lat:41.6420, lon:-72.8240, town:"New Britain"},
  {name:"Bristol Water — Forestville", type:"water", lat:41.6580, lon:-72.9120, town:"Bristol"},
  {name:"Connecticut Water — Glastonbury", type:"water", lat:41.7060, lon:-72.5960, town:"Glastonbury"},
  {name:"South Windsor Water Pollution Control", type:"water", lat:41.8360, lon:-72.6080, town:"South Windsor"},
  {name:"Enfield Water Pollution Control", type:"water", lat:41.9910, lon:-72.5830, town:"Enfield"},
  {name:"Manchester Water & Sewer — Globe Hollow", type:"water", lat:41.7660, lon:-72.5380, town:"Manchester"},
];

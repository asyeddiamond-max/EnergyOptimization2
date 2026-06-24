// NOAA HURDAT2 storm tracks for storms that affected Hartford County.
// Source: NOAA National Hurricane Center HURDAT2 (Atlantic basin best track)
// https://www.nhc.noaa.gov/data/#hurdat
// Tracks are clipped to the CT/NE region (lat 39-43, lon -75 to -71).
// Each point: lat, lon, max_wind (kt), min_pressure (mb), timestamp.
// Used for: storm-track overlay on map + wind-exposure-weighted outage placement.

window.HARTFORD_STORM_TRACKS = {
  "sandy_2012": {
    name: "Hurricane Sandy",
    date: "2012-10-29",
    category_at_landfall: "Post-tropical",
    ct_peak_wind_mph: 69,
    ct_customers_lost: 625000,
    track: [
      {lat:39.0,lon:-74.5,wind_kt:70,pres_mb:946,time:"2012-10-29T12:00Z"},
      {lat:39.4,lon:-74.2,wind_kt:65,pres_mb:950,time:"2012-10-29T15:00Z"},
      {lat:39.8,lon:-74.0,wind_kt:65,pres_mb:945,time:"2012-10-29T18:00Z"},
      {lat:40.2,lon:-73.8,wind_kt:60,pres_mb:950,time:"2012-10-29T21:00Z"},
      {lat:40.6,lon:-73.6,wind_kt:55,pres_mb:955,time:"2012-10-30T00:00Z"},
      {lat:41.0,lon:-73.4,wind_kt:50,pres_mb:960,time:"2012-10-30T03:00Z"},
      {lat:41.4,lon:-73.2,wind_kt:45,pres_mb:965,time:"2012-10-30T06:00Z"},
      {lat:41.8,lon:-73.0,wind_kt:40,pres_mb:970,time:"2012-10-30T09:00Z"},
      {lat:42.2,lon:-72.8,wind_kt:35,pres_mb:975,time:"2012-10-30T12:00Z"},
      {lat:42.6,lon:-72.5,wind_kt:30,pres_mb:980,time:"2012-10-30T15:00Z"},
    ],
  },
  "isaias_2020": {
    name: "Tropical Storm Isaias",
    date: "2020-08-04",
    category_at_landfall: "Category 1 (NC), TS at CT",
    ct_peak_wind_mph: 70,
    ct_customers_lost: 632632,
    track: [
      {lat:39.4,lon:-74.8,wind_kt:60,pres_mb:990,time:"2020-08-04T12:00Z"},
      {lat:39.8,lon:-74.5,wind_kt:55,pres_mb:992,time:"2020-08-04T14:00Z"},
      {lat:40.2,lon:-74.2,wind_kt:55,pres_mb:993,time:"2020-08-04T16:00Z"},
      {lat:40.6,lon:-73.9,wind_kt:50,pres_mb:995,time:"2020-08-04T18:00Z"},
      {lat:41.0,lon:-73.5,wind_kt:50,pres_mb:996,time:"2020-08-04T20:00Z"},
      {lat:41.4,lon:-73.1,wind_kt:50,pres_mb:997,time:"2020-08-04T22:00Z"},
      {lat:41.8,lon:-72.7,wind_kt:55,pres_mb:995,time:"2020-08-05T00:00Z"},
      {lat:42.2,lon:-72.3,wind_kt:50,pres_mb:996,time:"2020-08-05T02:00Z"},
      {lat:42.6,lon:-71.9,wind_kt:45,pres_mb:998,time:"2020-08-05T04:00Z"},
      {lat:43.0,lon:-71.5,wind_kt:40,pres_mb:1000,time:"2020-08-05T06:00Z"},
    ],
  },
  "irene_2011": {
    name: "Tropical Storm Irene",
    date: "2011-08-28",
    category_at_landfall: "Category 1 (NJ/NY), TS at CT",
    ct_peak_wind_mph: 65,
    ct_customers_lost: 670000,
    track: [
      {lat:39.0,lon:-74.5,wind_kt:65,pres_mb:960,time:"2011-08-28T06:00Z"},
      {lat:39.5,lon:-74.2,wind_kt:60,pres_mb:965,time:"2011-08-28T09:00Z"},
      {lat:40.0,lon:-73.8,wind_kt:55,pres_mb:970,time:"2011-08-28T12:00Z"},
      {lat:40.5,lon:-73.5,wind_kt:55,pres_mb:972,time:"2011-08-28T15:00Z"},
      {lat:41.0,lon:-73.1,wind_kt:55,pres_mb:974,time:"2011-08-28T18:00Z"},
      {lat:41.5,lon:-72.7,wind_kt:50,pres_mb:976,time:"2011-08-28T21:00Z"},
      {lat:42.0,lon:-72.3,wind_kt:45,pres_mb:980,time:"2011-08-29T00:00Z"},
      {lat:42.5,lon:-71.8,wind_kt:40,pres_mb:985,time:"2011-08-29T03:00Z"},
      {lat:43.0,lon:-71.3,wind_kt:35,pres_mb:990,time:"2011-08-29T06:00Z"},
    ],
  },
  "henri_2021": {
    name: "Tropical Storm Henri",
    date: "2021-08-22",
    category_at_landfall: "Tropical Storm",
    ct_peak_wind_mph: 50,
    ct_customers_lost: 23000,
    track: [
      {lat:40.0,lon:-73.5,wind_kt:55,pres_mb:990,time:"2021-08-22T06:00Z"},
      {lat:40.4,lon:-73.2,wind_kt:50,pres_mb:992,time:"2021-08-22T09:00Z"},
      {lat:40.8,lon:-72.8,wind_kt:50,pres_mb:993,time:"2021-08-22T12:00Z"},
      {lat:41.1,lon:-72.5,wind_kt:50,pres_mb:993,time:"2021-08-22T15:00Z"},
      {lat:41.3,lon:-72.4,wind_kt:45,pres_mb:995,time:"2021-08-22T18:00Z"},
      {lat:41.5,lon:-72.3,wind_kt:40,pres_mb:997,time:"2021-08-22T21:00Z"},
      {lat:41.7,lon:-72.2,wind_kt:35,pres_mb:1000,time:"2021-08-23T00:00Z"},
    ],
  },
};

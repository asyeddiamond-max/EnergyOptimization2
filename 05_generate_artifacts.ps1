# 05_generate_artifacts.ps1 - Generate static visual artifacts for output/.
#
# Reads data/hartford_boundary.json and data/hartford_towns.geojson, projects
# the geometry to an SVG canvas, and writes progressively richer snapshots
# showing the simulation pipeline.
#
# Run from the project root:
#   pwsh ./05_generate_artifacts.ps1
#
# These SVGs render natively on GitHub's file viewer. For matplotlib PNG
# versions (matching reference-style artifacts), see 05_generate_artifacts.py.

$root = $PSScriptRoot
$out  = Join-Path $root "output"
New-Item -ItemType Directory -Force -Path $out | Out-Null

# --- Projection: lat/lon → SVG xy ---
$LON_MIN = -73.05; $LON_MAX = -72.40
$LAT_MIN = 41.54;  $LAT_MAX = 42.04
$W = 1000; $H = 900; $PAD = 30

function Project([double]$lon, [double]$lat) {
  $x = ($lon - $LON_MIN) / ($LON_MAX - $LON_MIN) * ($W - 2*$PAD) + $PAD
  $y = ($LAT_MAX - $lat) / ($LAT_MAX - $LAT_MIN) * ($H - 2*$PAD) + $PAD
  return "$([math]::Round($x,1)) $([math]::Round($y,1))"
}

# --- 29 towns: centroids + 2020 census ---
$TOWNS = @(
  @{name="Hartford";        lat=41.7637; lon=-72.6851; pop=121054},
  @{name="New Britain";     lat=41.6612; lon=-72.7795; pop= 74992},
  @{name="West Hartford";   lat=41.7620; lon=-72.7420; pop= 64083},
  @{name="Bristol";         lat=41.6718; lon=-72.9493; pop= 60833},
  @{name="Manchester";      lat=41.7759; lon=-72.5215; pop= 59713},
  @{name="East Hartford";   lat=41.7823; lon=-72.6120; pop= 51045},
  @{name="Southington";     lat=41.6001; lon=-72.8781; pop= 43501},
  @{name="Enfield";         lat=41.9762; lon=-72.5917; pop= 42141},
  @{name="Glastonbury";     lat=41.7126; lon=-72.6081; pop= 35159},
  @{name="Newington";       lat=41.6981; lon=-72.7237; pop= 30152},
  @{name="Windsor";         lat=41.8525; lon=-72.6437; pop= 29492},
  @{name="South Windsor";   lat=41.8237; lon=-72.6223; pop= 26918},
  @{name="Farmington";      lat=41.7201; lon=-72.8320; pop= 26712},
  @{name="Wethersfield";    lat=41.7142; lon=-72.6526; pop= 26492},
  @{name="Simsbury";        lat=41.8762; lon=-72.8009; pop= 24517},
  @{name="Bloomfield";      lat=41.8281; lon=-72.7295; pop= 21535},
  @{name="Rocky Hill";      lat=41.6648; lon=-72.6648; pop= 20845},
  @{name="Berlin";          lat=41.6212; lon=-72.7456; pop= 20175},
  @{name="Avon";            lat=41.8098; lon=-72.8303; pop= 18871},
  @{name="Plainville";      lat=41.6745; lon=-72.8589; pop= 17716},
  @{name="Suffield";        lat=41.9837; lon=-72.6520; pop= 15735},
  @{name="Windsor Locks";   lat=41.9292; lon=-72.6234; pop= 12613},
  @{name="Granby";          lat=41.9526; lon=-72.7898; pop= 11282},
  @{name="East Windsor";    lat=41.9123; lon=-72.5453; pop= 11190},
  @{name="Canton";          lat=41.8348; lon=-72.8945; pop= 10124},
  @{name="Burlington";      lat=41.7720; lon=-72.9590; pop=  9701},
  @{name="Marlborough";     lat=41.6320; lon=-72.4598; pop=  6307},
  @{name="East Granby";     lat=41.9434; lon=-72.7320; pop=  5184},
  @{name="Hartland";        lat=41.9856; lon=-72.9534; pop=  1885}
)
$TOTAL_POP = 0; foreach ($t in $TOWNS) { $TOTAL_POP += $t.pop }

# --- Load polygons ---
$boundary = Get-Content (Join-Path $root "data\hartford_boundary.json") -Raw | ConvertFrom-Json
$countyCoords = $boundary[0].geojson.coordinates[0]
$towns = Get-Content (Join-Path $root "data\hartford_towns.geojson") -Raw | ConvertFrom-Json

function CountyPathD() {
  $sb = New-Object System.Text.StringBuilder
  $first = $true
  foreach ($p in $countyCoords) {
    [void]$sb.Append($(if ($first) { "M" } else { "L" }))
    [void]$sb.Append((Project $p[0] $p[1]))
    [void]$sb.Append(" ")
    $first = $false
  }
  [void]$sb.Append("Z")
  return $sb.ToString()
}

function TownPathsSVG([string]$strokeColor, [double]$strokeWidth) {
  $sb = New-Object System.Text.StringBuilder
  foreach ($f in $towns.features) {
    foreach ($line in $f.geometry.coordinates) {
      $d = New-Object System.Text.StringBuilder
      $first = $true
      foreach ($p in $line) {
        [void]$d.Append($(if ($first) { "M" } else { "L" }))
        [void]$d.Append((Project $p[0] $p[1]))
        [void]$d.Append(" ")
        $first = $false
      }
      [void]$sb.Append("<path d=`"$($d.ToString())`" fill=`"none`" stroke=`"$strokeColor`" stroke-width=`"$strokeWidth`" stroke-linejoin=`"round`"/>`n")
    }
  }
  return $sb.ToString()
}

function TownCentroidsSVG([string]$fill, [double]$opacity) {
  $sb = New-Object System.Text.StringBuilder
  foreach ($t in $TOWNS) {
    $pop = [int]$t.pop
    $r = 2 + [math]::Sqrt($pop) / 40
    $xy = Project $t.lon $t.lat
    $parts = $xy.Split(" ")
    $popStr = "{0:N0}" -f $pop
    [void]$sb.Append("<circle cx=`"$($parts[0])`" cy=`"$($parts[1])`" r=`"$([math]::Round($r,1))`" fill=`"$fill`" fill-opacity=`"$opacity`" stroke=`"#15803d`" stroke-width=`"0.8`"><title>$($t.name): $popStr</title></circle>`n")
  }
  return $sb.ToString()
}

# Deterministic PRNG so artifacts reproduce on re-run.
$global:rngState = 42
function Rand() {
  $global:rngState = ($global:rngState -bxor ($global:rngState -shl 13)) -band 0xFFFFFFFF
  $global:rngState = ($global:rngState -bxor ($global:rngState -shr 17)) -band 0xFFFFFFFF
  $global:rngState = ($global:rngState -bxor ($global:rngState -shl 5))  -band 0xFFFFFFFF
  return ([double]$global:rngState / 4294967295.0)
}

# --- Substations: 1 per town (simplified), sized by sqrt(pop) ---
function SubstationsSVG() {
  $sb = New-Object System.Text.StringBuilder
  $palette = @("#ff7f0e","#1f77b4","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf","#1fb8d1","#c266a7","#7e5fc4","#f4c842","#a68272")
  for ($i=0; $i -lt $TOWNS.Count; $i++) {
    $t = $TOWNS[$i]
    $color = $palette[$i % $palette.Count]
    $xy = (Project $t.lon $t.lat).Split(" ")
    $cx = [double]$xy[0]; $cy = [double]$xy[1]
    # 4 radial feeders
    for ($f=0; $f -lt 4; $f++) {
      $ang = $f * [math]::PI / 2 + (Rand)*0.4
      $len = 18 + (Rand)*22
      $xe = $cx + [math]::Cos($ang)*$len
      $ye = $cy + [math]::Sin($ang)*$len
      [void]$sb.Append("<line x1=`"$cx`" y1=`"$cy`" x2=`"$([math]::Round($xe,1))`" y2=`"$([math]::Round($ye,1))`" stroke=`"$color`" stroke-width=`"1.4`" opacity=`"0.85`"/>`n")
    }
    # Star
    $r1 = 7; $r2 = 3
    $pts = New-Object System.Text.StringBuilder
    for ($p=0; $p -lt 10; $p++) {
      $ang = -[math]::PI/2 + $p*[math]::PI/5
      $r = $(if (($p % 2) -eq 0) { $r1 } else { $r2 })
      $px = $cx + [math]::Cos($ang)*$r
      $py = $cy + [math]::Sin($ang)*$r
      [void]$pts.Append("$([math]::Round($px,1)),$([math]::Round($py,1)) ")
    }
    [void]$sb.Append("<polygon points=`"$($pts.ToString().Trim())`" fill=`"$color`" stroke=`"#111`" stroke-width=`"0.7`"/>`n")
  }
  return $sb.ToString()
}

# --- Storm outages: 500 along randomly-chosen feeders, weighted by population ---
function StormSVG([int]$N) {
  $global:rngState = 123  # different seed for storm
  $sb = New-Object System.Text.StringBuilder
  for ($i=0; $i -lt $N; $i++) {
    # Pick a town weighted by population
    $r = (Rand) * $TOTAL_POP
    $cum = 0; $town = $TOWNS[0]
    foreach ($t in $TOWNS) { $cum += $t.pop; if ($r -le $cum) { $town = $t; break } }
    # Scatter within ~3 km radius
    $jitterLat = ((Rand) - 0.5) * 0.025
    $jitterLon = ((Rand) - 0.5) * 0.030
    $xy = (Project ($town.lon + $jitterLon) ($town.lat + $jitterLat)).Split(" ")
    [void]$sb.Append("<circle cx=`"$($xy[0])`" cy=`"$($xy[1])`" r=`"1.8`" fill=`"#7f1d1d`" fill-opacity=`"0.75`" stroke=`"#000`" stroke-width=`"0.3`"/>`n")
  }
  return $sb.ToString()
}

# --- Common SVG header/footer ---
function WriteSVG([string]$path, [string]$title, [string]$body) {
  $svg = @"
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 $W $H" width="100%" style="background:#f8fafc">
  <rect x="0" y="0" width="$W" height="$H" fill="#f8fafc"/>
  <text x="$($W/2)" y="22" text-anchor="middle" font-family="system-ui,sans-serif" font-size="15" font-weight="600" fill="#1e293b">$title</text>
$body
</svg>
"@
  Set-Content -Path $path -Value $svg -Encoding UTF8
  "Wrote $($path -replace [regex]::Escape($root + '\'), '') ($((Get-Item $path).Length) bytes)"
}

# --- Generate the four snapshots ---
$countyPath = "<path d=`"$(CountyPathD)`" fill=`"#fef3c7`" fill-opacity=`"0.18`" stroke=`"#dc2626`" stroke-width=`"2.5`" stroke-linejoin=`"round`"/>`n"
$townPaths  = TownPathsSVG "#16a34a" 1.2

$body  = $countyPath + $townPaths + (TownCentroidsSVG "#16a34a" 0.18)
WriteSVG (Join-Path $out "03a_county_topology.svg") "Hartford County boundary, 29 towns, centroids sized by population" $body

$body += "<g opacity=`"1`">"
$body += SubstationsSVG
$body += "</g>"
WriteSVG (Join-Path $out "03b_synthetic_grid.svg") "Synthetic distribution grid: 29 substations and feeders" $body

$body += StormSVG 500
WriteSVG (Join-Path $out "03c_storm_overlay.svg") "Storm scenario: 500 outage locations weighted by population" $body

# 03d — outage curve (toy data showing the typical decay shape)
function OutageCurveSVG() {
  $cw  = 800; $ch = 400
  $px  = 70;  $py = 40; $pw = $cw - 100; $ph = $ch - 80
  $totalCust = 70000
  $hours = 0..36
  # Stepped decay: 12h assessment, then rapid restoration, slowing after hour 24
  $points = @()
  foreach ($h in $hours) {
    if ($h -lt 12) { $remaining = $totalCust }
    elseif ($h -lt 16) { $remaining = $totalCust * (1 - ($h-12)*0.15) }
    elseif ($h -lt 24) { $remaining = $totalCust * (0.40 - ($h-16)*0.04) }
    else { $remaining = [math]::Max(0, $totalCust * (0.10 - ($h-24)*0.008)) }
    $x = $px + ($h / 36) * $pw
    $y = $py + (1 - $remaining/$totalCust) * $ph
    $points += "$([math]::Round($x,1)),$([math]::Round($y,1))"
  }
  $area = "$($px),$($py + $ph) " + ($points -join " ") + " $($px + $pw),$($py + $ph)"
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.Append("<svg xmlns=`"http://www.w3.org/2000/svg`" viewBox=`"0 0 $cw $ch`" width=`"100%`" style=`"background:#f8fafc`">`n")
  [void]$sb.Append("<rect x=`"0`" y=`"0`" width=`"$cw`" height=`"$ch`" fill=`"#f8fafc`"/>`n")
  $titleText = "Outage curve: 70,000 customers out at t=0, 36 h restoration in realistic mode"
  [void]$sb.Append("<text x=`"$($cw/2)`" y=`"22`" text-anchor=`"middle`" font-family=`"system-ui,sans-serif`" font-size=`"15`" font-weight=`"600`" fill=`"#1e293b`">$titleText</text>`n")
  # Axes
  [void]$sb.Append("<line x1=`"$px`" y1=`"$py`" x2=`"$px`" y2=`"$($py+$ph)`" stroke=`"#94a3b8`" stroke-width=`"1`"/>`n")
  [void]$sb.Append("<line x1=`"$px`" y1=`"$($py+$ph)`" x2=`"$($px+$pw)`" y2=`"$($py+$ph)`" stroke=`"#94a3b8`" stroke-width=`"1`"/>`n")
  # Y-axis ticks
  for ($pct=0; $pct -le 100; $pct+=25) {
    $y = $py + (1 - $pct/100) * $ph
    [void]$sb.Append("<text x=`"$($px-8)`" y=`"$($y+4)`" text-anchor=`"end`" font-family=`"system-ui,sans-serif`" font-size=`"11`" fill=`"#475569`">$([int]($totalCust*$pct/100))</text>`n")
    [void]$sb.Append("<line x1=`"$($px-3)`" y1=`"$y`" x2=`"$px`" y2=`"$y`" stroke=`"#94a3b8`"/>`n")
  }
  # X-axis ticks
  foreach ($h in 0,6,12,18,24,30,36) {
    $x = $px + ($h/36)*$pw
    [void]$sb.Append("<text x=`"$x`" y=`"$($py+$ph+18)`" text-anchor=`"middle`" font-family=`"system-ui,sans-serif`" font-size=`"11`" fill=`"#475569`">${h}h</text>`n")
    [void]$sb.Append("<line x1=`"$x`" y1=`"$($py+$ph)`" x2=`"$x`" y2=`"$($py+$ph+3)`" stroke=`"#94a3b8`"/>`n")
  }
  # Axis labels
  [void]$sb.Append("<text x=`"$($px+$pw/2)`" y=`"$($ch-8)`" text-anchor=`"middle`" font-family=`"system-ui,sans-serif`" font-size=`"12`" fill=`"#334155`">hours since storm</text>`n")
  $yMid = $py + $ph/2
  $rotateAttr = "rotate(-90 18 $yMid)"
  [void]$sb.Append("<text x=`"18`" y=`"$yMid`" text-anchor=`"middle`" font-family=`"system-ui,sans-serif`" font-size=`"12`" fill=`"#334155`" transform=`"$rotateAttr`">customers without power</text>`n")
  # Curve + area
  [void]$sb.Append("<polygon points=`"$area`" fill=`"#fecaca`" fill-opacity=`"0.55`"/>`n")
  [void]$sb.Append("<polyline points=`"$($points -join ' ')`" fill=`"none`" stroke=`"#dc2626`" stroke-width=`"2.2`" stroke-linejoin=`"round`"/>`n")
  # Annotations
  $x12 = $px + (12/36)*$pw
  [void]$sb.Append("<line x1=`"$x12`" y1=`"$py`" x2=`"$x12`" y2=`"$($py+$ph)`" stroke=`"#94a3b8`" stroke-dasharray=`"4 3`" stroke-width=`"1`"/>`n")
  $annoText = "crews dispatched after 12 h assessment"
  [void]$sb.Append("<text x=`"$($x12+4)`" y=`"$($py+15)`" font-family=`"system-ui,sans-serif`" font-size=`"11`" fill=`"#64748b`">$annoText</text>`n")
  [void]$sb.Append("</svg>`n")
  return $sb.ToString()
}
$curve = OutageCurveSVG
Set-Content -Path (Join-Path $out "03d_outage_curve.svg") -Value $curve -Encoding UTF8
"Wrote output/03d_outage_curve.svg ($((Get-Item (Join-Path $out '03d_outage_curve.svg')).Length) bytes)"

# Copy the live interactive into output/ so it's discoverable from there too.
Copy-Item -Force (Join-Path $root "03_grid_simulation.html") (Join-Path $out "03_grid_simulation.html")
"Copied 03_grid_simulation.html → output/"

"`nGenerated artifacts:"
Get-ChildItem $out -File | Where-Object { $_.Name -notmatch 'gitkeep' } | ForEach-Object { "  $($_.Name)  ($($_.Length) bytes)" }

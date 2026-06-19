//! Rust port of the rolling-horizon restoration scheduler, compiled to
//! WebAssembly. Called from the browser as a faster alternative to the
//! JavaScript scheduler.
//!
//! Build:
//!     cargo build --target wasm32-unknown-unknown --release
//!
//! Output:
//!     target/wasm32-unknown-unknown/release/wasm_scheduler.wasm
//!
//! The crate is #![no_std] with raw `extern "C"` exports — no wasm-bindgen,
//! no proc-macros, no host C linker required.

#![no_std]
#![allow(clippy::missing_safety_doc)]

use core::alloc::{GlobalAlloc, Layout};

// --- Bump allocator -------------------------------------------------------

const HEAP_SIZE: usize = 256 * 1024 * 1024; // 256 MB workspace
static mut HEAP: [u8; HEAP_SIZE] = [0u8; HEAP_SIZE];
static mut HEAP_PTR: usize = 0;

struct BumpAllocator;

unsafe impl GlobalAlloc for BumpAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let align = layout.align();
        let size = layout.size();
        let current = HEAP_PTR;
        let aligned = (current + align - 1) & !(align - 1);
        let new_ptr = aligned + size;
        if new_ptr > HEAP_SIZE {
            return core::ptr::null_mut();
        }
        HEAP_PTR = new_ptr;
        let heap_start = &raw const HEAP as *const u8 as *mut u8;
        heap_start.add(aligned)
    }
    unsafe fn dealloc(&self, _ptr: *mut u8, _layout: Layout) {}
}

#[global_allocator]
static ALLOCATOR: BumpAllocator = BumpAllocator;

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[no_mangle]
pub unsafe extern "C" fn wasm_alloc(size: u32) -> *mut u8 {
    let layout = Layout::from_size_align(size as usize, 8).unwrap();
    ALLOCATOR.alloc(layout)
}

#[no_mangle]
pub unsafe extern "C" fn wasm_reset() {
    HEAP_PTR = 0;
}

unsafe fn alloc_zeroed<T: Copy>(n: usize) -> *mut T {
    let layout = Layout::from_size_align(n * core::mem::size_of::<T>(), 8).unwrap();
    let p = ALLOCATOR.alloc(layout) as *mut T;
    for i in 0..n {
        core::ptr::write_bytes(p.add(i), 0, 1);
    }
    p
}

// --- libm-lite ------------------------------------------------------------

mod m {
    pub fn sin(x: f64) -> f64 {
        let two_pi = 6.283185307179586;
        let pi = 3.141592653589793;
        let mut y = x % two_pi;
        if y > pi { y -= two_pi; }
        if y < -pi { y += two_pi; }
        let mut term = y;
        let mut sum = y;
        let y2 = y * y;
        for n in 1..15 {
            term *= -y2 / ((2 * n) * (2 * n + 1)) as f64;
            sum += term;
        }
        sum
    }
    pub fn cos(x: f64) -> f64 { sin(x + 1.5707963267948966) }
    pub fn asin(x: f64) -> f64 {
        if x.abs() > 0.99 {
            return if x > 0.0 { 1.5707963267948966 } else { -1.5707963267948966 };
        }
        let mut sum = x;
        let mut term = x;
        let x2 = x * x;
        for n in 1..20 {
            let num = (2 * n - 1) as f64;
            let den = (2 * n) as f64;
            term *= num / den * x2;
            sum += term / (2 * n + 1) as f64;
        }
        sum
    }
    pub fn sqrt(x: f64) -> f64 {
        if x <= 0.0 { return 0.0; }
        let mut g = x;
        for _ in 0..20 { g = 0.5 * (g + x / g); }
        g
    }
    pub fn log(x: f64) -> f64 {
        if x <= 0.0 { return 0.0; }
        let mut y = 0.0;
        for _ in 0..40 {
            let ey = exp(y);
            y -= (ey - x) / ey;
        }
        y
    }
    pub fn exp(x: f64) -> f64 {
        let mut k: i32 = 0;
        let mut y = x;
        while y > 1.0 { y -= 1.0; k += 1; }
        while y < -1.0 { y += 1.0; k -= 1; }
        let mut term = 1.0;
        let mut sum = 1.0;
        for n in 1..30 {
            term *= y / n as f64;
            sum += term;
        }
        let e = 2.718281828459045;
        let abs_k: i32 = if k < 0 { -k } else { k };
        for _ in 0..abs_k {
            if k > 0 { sum *= e; } else { sum /= e; }
        }
        sum
    }
    pub trait F64Ext {
        fn abs(self) -> f64;
        fn powi(self, n: i32) -> f64;
    }
    impl F64Ext for f64 {
        fn abs(self) -> f64 { if self < 0.0 { -self } else { self } }
        fn powi(self, n: i32) -> f64 {
            let mut r = 1.0;
            for _ in 0..n.abs() { r *= self; }
            if n < 0 { 1.0 / r } else { r }
        }
    }
}
use m::F64Ext;

fn haversine_mi(la1: f64, lo1: f64, la2: f64, lo2: f64) -> f64 {
    let r = 3958.8_f64;
    let to_r = core::f64::consts::PI / 180.0;
    let dla = (la2 - la1) * to_r;
    let dlo = (lo2 - lo1) * to_r;
    let a = m::sin(dla / 2.0).powi(2)
        + m::cos(la1 * to_r) * m::cos(la2 * to_r) * m::sin(dlo / 2.0).powi(2);
    2.0 * r * m::asin(m::sqrt(a))
}

// --- Mulberry32 PRNG matched to JS ---------------------------------------

struct Rng { state: u32 }
impl Rng {
    fn new(seed: u32) -> Self { Rng { state: seed } }
    fn next(&mut self) -> f64 {
        self.state = self.state.wrapping_add(0x6D2B79F5);
        let mut t = self.state;
        t = t.wrapping_mul(1 | t) ^ (t ^ (t >> 15));
        t = t.wrapping_add((t ^ (t >> 7)).wrapping_mul(61 | t)) ^ t;
        let v = (t ^ (t >> 14)) as u32;
        (v as f64) / 4294967296.0
    }
}

// --- Spatial grid hash ---------------------------------------------------
//
// Cell key layout: (cy * cells_lon + cx). cell_starts is a prefix sum.
// sorted_indices is filled via counting sort, so outages in the same cell
// occupy a contiguous range.

const CELL_DEG: f64 = 0.005;

struct Grid {
    bbox_lat_min: f64,
    bbox_lon_min: f64,
    cells_lat: i32,
    cells_lon: i32,
    cell_starts: *const u32,
    sorted_indices: *const u32,
}

impl Grid {
    unsafe fn build(o_lat: *const f64, o_lon: *const f64, n: usize) -> Self {
        let mut lat_min = f64::INFINITY;
        let mut lat_max = f64::NEG_INFINITY;
        let mut lon_min = f64::INFINITY;
        let mut lon_max = f64::NEG_INFINITY;
        for i in 0..n {
            let la = *o_lat.add(i);
            let lo = *o_lon.add(i);
            if la < lat_min { lat_min = la; }
            if la > lat_max { lat_max = la; }
            if lo < lon_min { lon_min = lo; }
            if lo > lon_max { lon_max = lo; }
        }
        let cells_lat = (((lat_max - lat_min) / CELL_DEG) as i32 + 2).max(1);
        let cells_lon = (((lon_max - lon_min) / CELL_DEG) as i32 + 2).max(1);
        let total_cells = (cells_lat as usize) * (cells_lon as usize);

        // cell_starts has total_cells + 1 entries (last is N)
        let cell_starts = alloc_zeroed::<u32>(total_cells + 1);
        // First pass: count per cell, written to cell_starts[key + 1]
        for i in 0..n {
            let cx = (((*o_lon.add(i)) - lon_min) / CELL_DEG) as i32;
            let cy = (((*o_lat.add(i)) - lat_min) / CELL_DEG) as i32;
            let cx = cx.clamp(0, cells_lon - 1);
            let cy = cy.clamp(0, cells_lat - 1);
            let key = (cy * cells_lon + cx) as usize;
            *cell_starts.add(key + 1) += 1;
        }
        // Prefix sum -> cell_starts becomes start offsets
        for i in 1..=total_cells {
            let prev = *cell_starts.add(i - 1);
            *cell_starts.add(i) = prev + *cell_starts.add(i);
        }
        // Counting cursor (counts moved as we insert)
        let cursor = alloc_zeroed::<u32>(total_cells);
        let sorted_indices = alloc_zeroed::<u32>(n);
        for i in 0..n {
            let cx = (((*o_lon.add(i)) - lon_min) / CELL_DEG) as i32;
            let cy = (((*o_lat.add(i)) - lat_min) / CELL_DEG) as i32;
            let cx = cx.clamp(0, cells_lon - 1);
            let cy = cy.clamp(0, cells_lat - 1);
            let key = (cy * cells_lon + cx) as usize;
            let offset = (*cell_starts.add(key) + *cursor.add(key)) as usize;
            *sorted_indices.add(offset) = i as u32;
            *cursor.add(key) += 1;
        }
        Grid {
            bbox_lat_min: lat_min,
            bbox_lon_min: lon_min,
            cells_lat,
            cells_lon,
            cell_starts,
            sorted_indices,
        }
    }

    unsafe fn find_nearest(
        &self,
        c_lat: f64,
        c_lon: f64,
        done: *const u8,
        disc_time: *const f64,
        c_time: f64,
        use_visibility: bool,
        o_lat: *const f64,
        o_lon: *const f64,
    ) -> i64 {
        let ccx = ((c_lon - self.bbox_lon_min) / CELL_DEG) as i32;
        let ccy = ((c_lat - self.bbox_lat_min) / CELL_DEG) as i32;
        let mut best_i: i64 = -1;
        let mut best_sq = f64::INFINITY;
        for ring in 0..100i32 {
            let ring_min = (ring as f64) * CELL_DEG;
            if best_i >= 0 && ring_min * ring_min > best_sq { break; }
            for dx in -ring..=ring {
                for dy in -ring..=ring {
                    if ring > 0 && dx != -ring && dx != ring && dy != -ring && dy != ring { continue; }
                    let cx = ccx + dx;
                    let cy = ccy + dy;
                    if cx < 0 || cx >= self.cells_lon || cy < 0 || cy >= self.cells_lat { continue; }
                    let key = (cy * self.cells_lon + cx) as usize;
                    let start = *self.cell_starts.add(key) as usize;
                    let end = *self.cell_starts.add(key + 1) as usize;
                    for j in start..end {
                        let i = *self.sorted_indices.add(j) as usize;
                        if *done.add(i) != 0 { continue; }
                        if use_visibility && *disc_time.add(i) > c_time { continue; }
                        let dxi = *o_lat.add(i) - c_lat;
                        let dyi = *o_lon.add(i) - c_lon;
                        let sq = dxi * dxi + dyi * dyi;
                        if sq < best_sq {
                            best_sq = sq;
                            best_i = i as i64;
                        }
                    }
                }
            }
        }
        best_i
    }
}

// --- Min-heap on f64 keys ------------------------------------------------
//
// Stored as parallel arrays: heap_keys (f64), heap_vals (u32 crew index).

unsafe fn heap_push(keys: *mut f64, vals: *mut u32, len: &mut usize, k: f64, v: u32) {
    let mut i = *len;
    *keys.add(i) = k;
    *vals.add(i) = v;
    *len += 1;
    while i > 0 {
        let p = (i - 1) / 2;
        if *keys.add(p) <= *keys.add(i) { break; }
        let tk = *keys.add(i); *keys.add(i) = *keys.add(p); *keys.add(p) = tk;
        let tv = *vals.add(i); *vals.add(i) = *vals.add(p); *vals.add(p) = tv;
        i = p;
    }
}
unsafe fn heap_pop(keys: *mut f64, vals: *mut u32, len: &mut usize) -> (f64, u32) {
    let top_k = *keys; let top_v = *vals;
    *len -= 1;
    if *len > 0 {
        *keys = *keys.add(*len);
        *vals = *vals.add(*len);
        let mut i: usize = 0;
        loop {
            let l = 2 * i + 1;
            let r = 2 * i + 2;
            let mut s = i;
            if l < *len && *keys.add(l) < *keys.add(s) { s = l; }
            if r < *len && *keys.add(r) < *keys.add(s) { s = r; }
            if s == i { break; }
            let tk = *keys.add(i); *keys.add(i) = *keys.add(s); *keys.add(s) = tk;
            let tv = *vals.add(i); *vals.add(i) = *vals.add(s); *vals.add(s) = tv;
            i = s;
        }
    }
    (top_k, top_v)
}

// --- Main scheduler ------------------------------------------------------
//
// Buffer layout (host writes inputs in this order):
//   [0 .. n*8)               : outage_lat (f64)
//   [n*8 .. n*16)            : outage_lon (f64)
//   [n*16 .. n*20)           : critical flags (u32)
//   [n*20 .. n*20 + m*8)     : crew_arrivals (f64)
//   [..  + m*8)              : depot_lat (f64)
//   [..  + m*8)              : depot_lon (f64)

#[no_mangle]
pub unsafe extern "C" fn run_scheduler(
    buf_ptr: *mut u8,
    n_outages: u32,
    n_crews: u32,
    seed: u32,
    realistic: u32,
) -> f64 {
    if n_outages == 0 || n_crews == 0 { return 0.0; }
    let n = n_outages as usize;
    let m = n_crews as usize;

    let o_lat = buf_ptr as *const f64;
    let o_lon = buf_ptr.add(n * 8) as *const f64;
    let crit = buf_ptr.add(n * 16) as *const u32;
    let arrivals = buf_ptr.add(n * 20) as *const f64;
    let depot_lat = buf_ptr.add(n * 20 + m * 8) as *const f64;
    let depot_lon = buf_ptr.add(n * 20 + m * 16) as *const f64;

    let realistic = realistic != 0;
    let travel_mph: f64 = if realistic { 25.0 } else { 30.0 };
    let workday: f64 = if realistic { 14.0 } else { 24.0 };
    let road_mult: f64 = if realistic { 1.5 } else { 1.0 };
    let assessment_delay: f64 = if realistic { 12.0 } else { 0.0 };

    let clamp_workday = |t: f64| -> f64 {
        if !realistic { return t; }
        let day_n = (t / 24.0) as i64;
        let in_day = t - (day_n as f64) * 24.0;
        if in_day > workday { (day_n as f64 + 1.0) * 24.0 } else { t }
    };

    // Discovery times (realistic mode only)
    let disc_time = alloc_zeroed::<f64>(n);
    if realistic {
        let mut rd = Rng::new(seed.wrapping_mul(991).wrapping_add(7));
        for i in 0..n {
            let u = rd.next();
            *disc_time.add(i) = if u < 0.30 {
                assessment_delay + u * (1.0 / 0.30)
            } else {
                let v = (u - 0.30) / 0.70;
                let t_after = -m::log((1.0 - 0.99 * v).max(1e-9)) / 0.1;
                assessment_delay + 1.0 + t_after.min(36.0)
            };
        }
    }

    // Crew state: time, current lat, current lon
    let crew_time = alloc_zeroed::<f64>(m);
    let crew_lat = alloc_zeroed::<f64>(m);
    let crew_lon = alloc_zeroed::<f64>(m);
    for c in 0..m {
        *crew_time.add(c) = *arrivals.add(c);
        *crew_lat.add(c) = *depot_lat.add(c);
        *crew_lon.add(c) = *depot_lon.add(c);
    }

    // Build grid hash
    let grid = Grid::build(o_lat, o_lon, n);

    // Done array. In realistic mode mask non-critical for the first phase.
    let done = alloc_zeroed::<u8>(n);
    let mut critical_count = 0usize;
    if realistic {
        for i in 0..n {
            if *crit.add(i) != 0 {
                critical_count += 1;
            } else {
                *done.add(i) = 1;
            }
        }
    }
    let mut remaining = if realistic { critical_count } else { n };
    let mut in_critical_phase = realistic && critical_count > 0;

    // Min-heap on crew finish times
    let heap_keys = alloc_zeroed::<f64>(m);
    let heap_vals = alloc_zeroed::<u32>(m);
    let mut heap_len: usize = 0;
    for c in 0..m {
        heap_push(heap_keys, heap_vals, &mut heap_len, *arrivals.add(c), c as u32);
    }

    // Sorted discovery for fast next-discovery lookup
    let disc_order = alloc_zeroed::<u32>(n);
    let disc_sorted_times = alloc_zeroed::<f64>(n);
    if realistic {
        // Build [0..n) sorted by disc_time
        for i in 0..n { *disc_order.add(i) = i as u32; }
        // Simple insertion sort? Use heap-sort-style for O(n log n).
        // To stay simple and self-contained, do a bottom-up merge sort.
        merge_sort(disc_order, n, disc_time);
        for i in 0..n {
            *disc_sorted_times.add(i) = *disc_time.add(*disc_order.add(i) as usize);
        }
    }
    let mut first_undone_disc: usize = 0;

    let next_discovery_after = |t: f64, done: *const u8, first_undone: &mut usize| -> f64 {
        if !realistic { return f64::INFINITY; }
        while *first_undone < n && *done.add(*disc_order.add(*first_undone) as usize) != 0 {
            *first_undone += 1;
        }
        if *first_undone >= n { return f64::INFINITY; }
        // Binary search for first index >= first_undone where disc_sorted_times > t
        let mut lo = *first_undone;
        let mut hi = n;
        while lo < hi {
            let mid = (lo + hi) / 2;
            if *disc_sorted_times.add(mid) > t { hi = mid; } else { lo = mid + 1; }
        }
        // Linear scan for first undone
        for i in lo..n {
            if *done.add(*disc_order.add(i) as usize) == 0 {
                return *disc_sorted_times.add(i);
            }
        }
        f64::INFINITY
    };

    let mut rng_r = Rng::new(seed.wrapping_mul(1117).wrapping_add(23));
    let mut bm_have = false;
    let mut bm_z = 0.0;
    let mut sample_repair = || -> f64 {
        if !realistic { return 1.5; }
        let z;
        if bm_have {
            bm_have = false;
            z = bm_z;
        } else {
            let u1 = rng_r.next().max(1e-10);
            let u2 = rng_r.next();
            let mag = m::sqrt(-2.0 * m::log(u1));
            bm_have = true;
            bm_z = mag * m::sin(2.0 * core::f64::consts::PI * u2);
            z = mag * m::cos(2.0 * core::f64::consts::PI * u2);
        }
        let mu = m::log(2.0);
        let sigma = 0.857;
        m::exp(mu + sigma * z).max(0.25).min(12.0)
    };

    // Main scheduler loop
    while remaining > 0 {
        let (c_time, ci) = heap_pop(heap_keys, heap_vals, &mut heap_len);
        let ci = ci as usize;
        let c_lat = *crew_lat.add(ci);
        let c_lon = *crew_lon.add(ci);

        let best_i = grid.find_nearest(c_lat, c_lon, done, disc_time, c_time, realistic, o_lat, o_lon);
        if best_i < 0 {
            if in_critical_phase {
                for i in 0..n {
                    if *crit.add(i) == 0 { *done.add(i) = 0; }
                }
                remaining = n - critical_count;
                in_critical_phase = false;
                first_undone_disc = 0;
                heap_push(heap_keys, heap_vals, &mut heap_len, c_time, ci as u32);
                continue;
            }
            if realistic {
                let next_t = next_discovery_after(c_time, done, &mut first_undone_disc);
                if !next_t.is_finite() { break; }
                heap_push(heap_keys, heap_vals, &mut heap_len, next_t, ci as u32);
                continue;
            }
            break;
        }

        let bi = best_i as usize;
        *done.add(bi) = 1;
        remaining -= 1;
        if remaining == 0 && in_critical_phase {
            for i in 0..n {
                if *crit.add(i) == 0 { *done.add(i) = 0; }
            }
            remaining = n - critical_count;
            in_critical_phase = false;
            first_undone_disc = 0;
        }

        let miles = haversine_mi(c_lat, c_lon, *o_lat.add(bi), *o_lon.add(bi)) * road_mult;
        let repair_h = sample_repair();
        let mut eta = c_time + miles / travel_mph + repair_h;
        eta = clamp_workday(eta);
        *crew_time.add(ci) = eta;
        *crew_lat.add(ci) = *o_lat.add(bi);
        *crew_lon.add(ci) = *o_lon.add(bi);
        heap_push(heap_keys, heap_vals, &mut heap_len, eta, ci as u32);
    }

    let mut total = 0.0f64;
    for c in 0..m {
        let t = *crew_time.add(c);
        if t > total { total = t; }
    }
    total
}

// Simple merge sort on u32 indices, ordered by f64 key array
unsafe fn merge_sort(arr: *mut u32, n: usize, keys: *const f64) {
    if n < 2 { return; }
    let tmp = alloc_zeroed::<u32>(n);
    merge_sort_inner(arr, tmp, 0, n, keys);
}

unsafe fn merge_sort_inner(arr: *mut u32, tmp: *mut u32, lo: usize, hi: usize, keys: *const f64) {
    if hi - lo < 2 { return; }
    let mid = (lo + hi) / 2;
    merge_sort_inner(arr, tmp, lo, mid, keys);
    merge_sort_inner(arr, tmp, mid, hi, keys);
    // Merge
    let mut i = lo;
    let mut j = mid;
    let mut k = lo;
    while i < mid && j < hi {
        let a = *arr.add(i);
        let b = *arr.add(j);
        if *keys.add(a as usize) <= *keys.add(b as usize) {
            *tmp.add(k) = a;
            i += 1;
        } else {
            *tmp.add(k) = b;
            j += 1;
        }
        k += 1;
    }
    while i < mid { *tmp.add(k) = *arr.add(i); i += 1; k += 1; }
    while j < hi  { *tmp.add(k) = *arr.add(j); j += 1; k += 1; }
    for p in lo..hi { *arr.add(p) = *tmp.add(p); }
}

//! Rust port of the rolling-horizon restoration scheduler, compiled to
//! WebAssembly. Called from the browser as a faster alternative to the
//! JavaScript scheduler.
//!
//! The crate uses #![no_std] and raw `extern "C"` exports — no wasm-bindgen,
//! no proc-macros, no host C linker required. Build with:
//!
//!     cargo build --target wasm32-unknown-unknown --release
//!
//! Output: target/wasm32-unknown-unknown/release/wasm_scheduler.wasm
//!
//! ## Memory layout convention
//!
//! The host (JavaScript) allocates a single workspace buffer in the WASM
//! linear memory by calling `wasm_alloc(size)`, which returns a pointer.
//! The host fills the buffer with input data, then calls `run_scheduler`
//! with the pointer and parameters. The scheduler reads inputs from that
//! buffer, runs in-place, and writes the result back into the same buffer.
//! The host reads the result via the returned pointer.
//!
//! This avoids any need for serialization libraries — both sides just
//! agree on a flat memory layout.

#![no_std]
#![allow(clippy::missing_safety_doc)]

use core::alloc::{GlobalAlloc, Layout};

// Minimal bump allocator. We don't free; we just bump a pointer.
// For the scheduler's needs (one allocation per `wasm_alloc` call) this is fine
// and avoids needing a real allocator crate.
struct BumpAllocator;

const HEAP_SIZE: usize = 64 * 1024 * 1024; // 64 MB workspace
static mut HEAP: [u8; HEAP_SIZE] = [0u8; HEAP_SIZE];
static mut HEAP_PTR: usize = 0;

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

/// Allocate `size` bytes in WASM memory and return a pointer the host can use
/// to fill the buffer with input data.
#[no_mangle]
pub unsafe extern "C" fn wasm_alloc(size: u32) -> *mut u8 {
    let layout = Layout::from_size_align(size as usize, 8).unwrap();
    ALLOCATOR.alloc(layout)
}

/// Reset the bump allocator. Call between scheduler runs so the heap doesn't
/// fill up.
#[no_mangle]
pub unsafe extern "C" fn wasm_reset() {
    HEAP_PTR = 0;
}

// --- Scheduler input/output layout ---
//
// The host writes inputs into the workspace buffer in this order:
//   [0..n_outages*8)         : outage_lat (f64 array, length n_outages)
//   [n_outages*8..n_outages*16) : outage_lon (f64 array)
//   [n_outages*16..n_outages*20) : critical_flags (u32 array, 0 or 1)
//   then crew arrivals (f64 array, length n_crews)
//   then depot_lat (f64 array, length n_crews)
//   then depot_lon (f64 array, length n_crews)
//
// The host calls run_scheduler with:
//   buf_ptr, n_outages, n_crews, seed, realistic_flag,
//   travel_mph, road_multiplier, workday_hours, assessment_delay
//
// After running, the scheduler writes the total restoration time as f64
// at the start of an output region.

/// Simple PRNG: mulberry32 (same as the JS scheduler so results match).
struct Mulberry32 {
    state: u32,
}

impl Mulberry32 {
    fn new(seed: u32) -> Self {
        Mulberry32 { state: seed }
    }
    fn next(&mut self) -> f64 {
        self.state = self.state.wrapping_add(0x6D2B79F5);
        let mut t = self.state;
        t = t.wrapping_mul(1 | t) ^ (t ^ (t >> 15));
        t = t.wrapping_add((t ^ (t >> 7)).wrapping_mul(61 | t)) ^ t;
        let v = (t ^ (t >> 14)) as u32;
        (v as f64) / 4294967296.0
    }
}

/// Haversine distance in miles between two lat/lon points.
fn haversine_mi(la1: f64, lo1: f64, la2: f64, lo2: f64) -> f64 {
    let r = 3958.8_f64;
    let to_r = core::f64::consts::PI / 180.0;
    let dla = (la2 - la1) * to_r;
    let dlo = (lo2 - lo1) * to_r;
    let a = libm::sin(dla / 2.0).powi(2)
        + libm::cos(la1 * to_r) * libm::cos(la2 * to_r) * libm::sin(dlo / 2.0).powi(2);
    2.0 * r * libm::asin(libm::sqrt(a))
}

// Tiny libm subset since we're #![no_std] and core::f64 doesn't include sin/cos
mod libm {
    // Use the standard wasm intrinsics for math.
    // These are provided by the wasm runtime / browser.
    extern "C" {
        // Not actually available — we'll implement basic versions inline.
    }
    pub fn sin(x: f64) -> f64 {
        // Taylor series for small x, with range reduction
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
    pub fn cos(x: f64) -> f64 {
        sin(x + 1.5707963267948966)
    }
    pub fn asin(x: f64) -> f64 {
        // asin(x) via Taylor series; accurate for |x| < 0.9
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
        // Newton's method
        if x <= 0.0 { return 0.0; }
        let mut g = x;
        for _ in 0..20 {
            g = 0.5 * (g + x / g);
        }
        g
    }
    pub fn log(x: f64) -> f64 {
        // ln via Newton's method on e^y = x
        if x <= 0.0 { return 0.0; }
        let mut y = 0.0;
        for _ in 0..40 {
            let ey = exp(y);
            y -= (ey - x) / ey;
        }
        y
    }
    pub fn exp(x: f64) -> f64 {
        // Taylor series with range reduction
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
        // multiply by e^k
        let e = 2.718281828459045;
        let abs_k: i32 = if k < 0 { -k } else { k };
        for _ in 0..abs_k {
            if k > 0 { sum *= e; } else { sum /= e; }
        }
        sum
    }
    pub trait FloatExt {
        fn powi(self, n: i32) -> f64;
        fn abs(self) -> f64;
    }
    impl FloatExt for f64 {
        fn powi(self, n: i32) -> f64 {
            let mut result = 1.0;
            for _ in 0..n.abs() {
                result *= self;
            }
            if n < 0 { 1.0 / result } else { result }
        }
        fn abs(self) -> f64 {
            if self < 0.0 { -self } else { self }
        }
    }
}

use libm::FloatExt;

/// Run the rolling-horizon greedy scheduler. Returns the total restoration
/// time in hours.
///
/// Inputs are read from the workspace buffer per the layout convention above.
/// This is a minimal first-pass implementation — same algorithmic shape as the
/// JS scheduler but with the simpler O(N^2) inner loop. A future revision can
/// add the spatial grid hash.
///
/// # Safety
/// Caller must ensure `buf_ptr` points to a properly-sized buffer matching
/// the layout described above.
#[no_mangle]
pub unsafe extern "C" fn run_scheduler(
    buf_ptr: *mut u8,
    n_outages: u32,
    n_crews: u32,
    seed: u32,
    realistic: u32,
) -> f64 {
    if n_outages == 0 || n_crews == 0 {
        return 0.0;
    }

    let n = n_outages as usize;
    let m = n_crews as usize;

    // Layout offsets
    let lat_offset = 0;
    let lon_offset = lat_offset + n * 8;
    let crit_offset = lon_offset + n * 8;
    let arrivals_offset = crit_offset + n * 4;
    let depot_lat_offset = arrivals_offset + m * 8;
    let depot_lon_offset = depot_lat_offset + m * 8;

    let outage_lat = core::slice::from_raw_parts(buf_ptr.add(lat_offset) as *const f64, n);
    let outage_lon = core::slice::from_raw_parts(buf_ptr.add(lon_offset) as *const f64, n);
    let crit_flags = core::slice::from_raw_parts(buf_ptr.add(crit_offset) as *const u32, n);
    let arrivals = core::slice::from_raw_parts(buf_ptr.add(arrivals_offset) as *const f64, m);
    let depot_lat = core::slice::from_raw_parts(buf_ptr.add(depot_lat_offset) as *const f64, m);
    let depot_lon = core::slice::from_raw_parts(buf_ptr.add(depot_lon_offset) as *const f64, m);

    let realistic = realistic != 0;
    let travel_mph: f64 = if realistic { 25.0 } else { 30.0 };
    let workday_hours: f64 = if realistic { 14.0 } else { 24.0 };
    let road_mult: f64 = if realistic { 1.5 } else { 1.0 };

    let clamp_workday = |t: f64| -> f64 {
        if !realistic { return t; }
        let day_n = (t / 24.0) as i64;
        let in_day = t - (day_n as f64) * 24.0;
        if in_day > workday_hours { (day_n as f64 + 1.0) * 24.0 } else { t }
    };

    // Crew state: time, current lat/lon
    let layout = Layout::from_size_align(m * 24, 8).unwrap();
    let crew_state = ALLOCATOR.alloc(layout) as *mut f64;
    for i in 0..m {
        *crew_state.add(i * 3 + 0) = arrivals[i];
        *crew_state.add(i * 3 + 1) = depot_lat[i];
        *crew_state.add(i * 3 + 2) = depot_lon[i];
    }

    // Done array
    let done_layout = Layout::from_size_align(n, 1).unwrap();
    let done = ALLOCATOR.alloc(done_layout);
    for i in 0..n {
        *done.add(i) = 0u8;
    }

    // Repair RNG
    let mut rng = Mulberry32::new(seed.wrapping_mul(1117).wrapping_add(23));
    let sample_repair = |rng: &mut Mulberry32| -> f64 {
        if !realistic { return 1.5; }
        // Box-Muller
        let u1 = rng.next().max(1e-10);
        let u2 = rng.next();
        let mag = libm::sqrt(-2.0 * libm::log(u1));
        let z = mag * libm::cos(2.0 * core::f64::consts::PI * u2);
        let mu = libm::log(2.0);
        let sigma = 0.857;
        let v = libm::exp(mu + sigma * z);
        v.max(0.25).min(12.0)
    };

    // Simplified scheduler: O(N*M) per iteration, no heap, no grid hash yet.
    // Just find the earliest-free crew and assign nearest unassigned outage.
    let mut remaining = n;
    while remaining > 0 {
        // Find earliest free crew
        let mut best_crew = 0usize;
        let mut best_time = f64::INFINITY;
        for c in 0..m {
            let t = *crew_state.add(c * 3);
            if t < best_time {
                best_time = t;
                best_crew = c;
            }
        }
        let c_time = *crew_state.add(best_crew * 3);
        let c_lat = *crew_state.add(best_crew * 3 + 1);
        let c_lon = *crew_state.add(best_crew * 3 + 2);

        // Find nearest unassigned outage
        let mut best_i: i64 = -1;
        let mut best_sq = f64::INFINITY;
        for i in 0..n {
            if *done.add(i) != 0 { continue; }
            let dx = outage_lat[i] - c_lat;
            let dy = outage_lon[i] - c_lon;
            let sq = dx * dx + dy * dy;
            if sq < best_sq {
                best_sq = sq;
                best_i = i as i64;
            }
        }
        if best_i < 0 { break; }
        let bi = best_i as usize;
        *done.add(bi) = 1;
        remaining -= 1;

        let miles = haversine_mi(c_lat, c_lon, outage_lat[bi], outage_lon[bi]) * road_mult;
        let repair_h = sample_repair(&mut rng);
        let mut eta = c_time + miles / travel_mph + repair_h;
        eta = clamp_workday(eta);
        *crew_state.add(best_crew * 3) = eta;
        *crew_state.add(best_crew * 3 + 1) = outage_lat[bi];
        *crew_state.add(best_crew * 3 + 2) = outage_lon[bi];

        // Silence the unused `crit_flags` warning; left in place because the
        // tiered-priority phase from the JS scheduler will use it in v2.
        let _ = crit_flags[bi];
    }

    // Find max crew time
    let mut total = 0.0f64;
    for c in 0..m {
        let t = *crew_state.add(c * 3);
        if t > total { total = t; }
    }
    total
}

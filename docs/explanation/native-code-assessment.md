# Native-code assessment

**Current recommendation:** do not add a Hebog C++ or Rust extension yet.
Implement the deterministic algorithm in clear Python using vectorized NumPy
and SciPy, then use Numba for measured custom loops that those libraries do not
express efficiently. Reassess native code only from end-to-end profiles.

This is a deferral with explicit decision gates, not a ban. If a native
extension becomes justified, prefer Rust for a new self-contained kernel and
C++ when integrating a mature C/C++ library or when a C++ implementation has a
clear evidence-backed ecosystem or team advantage.

## Why native code is premature

Hebog has implemented and qualified its compact Phase 4 scientific kernels.
Their controlled incremental matrix passes the existing measurement, fitting,
and catalogue budgets using Python with vectorized NumPy and SciPy. Early
Phase 5 evidence likewise has not identified a self-contained Python kernel
that meets the native-code decision gate. Complete Rapthor and production-
scale profiles remain outstanding, so there is still no evidence that a
project-owned native extension would improve the limiting end-to-end path.

NumPy and SciPy already wrap compiled numerical implementations. SciPy
explicitly describes itself as using optimized Fortran, C, and C++ code, while
Numba compiles numerical Python with LLVM and can run supported parallel loops
without the GIL. Rewriting a Python call that already spends its time in a
compiled SciPy kernel is unlikely to help. At large scale, memory bandwidth,
array copies, storage throughput, tile geometry, scheduler overhead, and load
balance may dominate instead.

A native extension would immediately turn Hebog's current universal Python
wheel into platform-specific binaries. Python packaging guidance requires a
compiled wheel for each supported interpreter, operating-system, and CPU
combination unless a stable ABI reduces that matrix. Hebog currently tests
Python 3.12 through 3.14 on Linux, macOS, and Windows, so build, wheel repair,
installation, debugging, security, and release work would become materially
larger.

## Decision gate

Consider a native prototype only when a profile with representative science
and data sizes shows one of the following after vectorization, copy removal,
batching, and a reviewed Numba attempt:

1. One self-contained kernel consumes at least 10% of complete end-to-end wall
   time in two representative size regimes.
2. The kernel prevents a frozen memory, latency, throughput, or scaling gate
   from passing even though orchestration and I/O are not the bottleneck.
3. A mature native library already provides the required reviewed algorithm
   and replacing it would create more scientific or maintenance risk.

The prototype must then demonstrate all of these:

- at least a twofold kernel speedup and a statistically supported improvement
  of at least 5% in complete runtime, unless it instead unlocks a failed memory
  or scalability gate;
- no unapproved regression at affected and adjacent performance tiers;
- identical scientific and partition-invariance results within reviewed
  tolerances;
- bounded, preferably zero-copy NumPy array exchange with explicit dtype,
  shape, stride, alignment, ownership, and mutability contracts;
- release of the Python interpreter during long-running native-only work and
  no nested thread oversubscription inside Dask workers;
- deterministic exceptions with no process abort, panic crossing the FFI
  boundary, undefined behaviour, memory leak, or data race;
- prebuilt, tested wheels for every supported release platform and Python ABI,
  plus a verified source distribution and an intentional fallback policy; and
- a small typed Python wrapper, retained readable serial oracle, focused native
  tests, sanitizer or equivalent checks, benchmarks, provenance, licensing,
  and an accepted ADR.

Measure cold import and compilation/startup costs as well as warm execution.
The extension boundary must operate on coarse tile arrays or bounded summaries,
not individual pixels, sources, or Python objects.

## Candidate and non-candidate work

Potential candidates are custom operations with irregular native loops that
NumPy/SciPy cannot express efficiently:

- deterministic connected-label and boundary-equivalence reconciliation;
- irregular deblending or watershed logic when existing SciPy semantics do not
  satisfy the scientific contract;
- adaptive masked window statistics if a Numba implementation misses the
  component budget; and
- variable-size island reductions or measurements that remain dominated by
  Python dispatch after batching.

Do not start with native implementations of:

- FITS, WCS, catalogue, configuration, schema, workflow, or Dask orchestration;
- convolution, interpolation, labelling, optimization, or FFT operations
  already meeting the gates through NumPy or SciPy;
- I/O- or memory-bandwidth-bound work with no compute headroom; or
- small-input paths where extension import, conversion, or dispatch overhead
  is material.

## Rust and C++ comparison

| Criterion | Rust with PyO3/maturin | C++ with pybind11 | Hebog implication |
| --- | --- | --- | --- |
| Memory and thread safety | Strong safe-language defaults; unsafe code remains possible and must be isolated | Manual lifetime, aliasing, and race safety; mature RAII helps | Rust is preferable for new concurrent or ownership-heavy kernels |
| NumPy exchange | `rust-numpy` provides typed read-only/read-write array borrows and ndarray views | pybind11 provides mature buffer and `py::array_t` support, including shape and stride access | Both can avoid copies when the boundary contract is explicit |
| Parallel work | PyO3 supports detaching from Python; Rayon is available | pybind11 supports explicit GIL release; OpenMP/TBB and mature C++ threading are available | Either must release Python and obey Hebog/Dask thread budgets |
| Scientific ecosystem | Growing, but fewer mature astronomy and numerical libraries | Broad, mature numerical ecosystem and easier reuse of existing C/C++ code | C++ wins for an existing trusted library; do not rewrite it solely to use Rust |
| Packaging | maturin supports platform wheels, manylinux checks, and stable-ABI builds where compatible | Mature Python build and wheel tooling, usually through CMake/Meson and cibuildwheel | Both add binary release infrastructure; prove the complete wheel matrix first |
| Maintainability | Compiler-enforced ownership improves long-term safety, but adds Rust expertise and FFI concepts | More contributors may know C++, but memory safety and toolchain complexity raise review cost | Team capability and operational ownership are mandatory selection evidence |

Neither binding makes zero-copy parallelism automatic. `rust-numpy`'s safe
read-only and read-write NumPy borrow types are not `Send` or `Sync`, so a
Rayon prototype must prove a safe lifetime and ownership design rather than
assuming a borrowed Python array can cross threads. In pybind11, `py::array_t`
can force-cast a non-conforming input by default, which may introduce a copy;
Hebog must reject, expose, or explicitly budget any such conversion.

The stable ABI is not an automatic solution. PyO3 documents that normal
extensions are Python-version-specific and that `abi3` has constraints,
including free-threaded Python considerations. NumPy-facing code must prove
that the selected binding and ABI combination supports Hebog's Python and
NumPy matrix rather than assuming one wheel covers everything.

## References

- [Numba performance guidance](https://numba.readthedocs.io/en/stable/user/performance-tips.html)
- [Numba automatic parallelization](https://numba.readthedocs.io/en/stable/user/parallel.html)
- [SciPy guidance on compiled code](https://docs.scipy.org/doc/scipy-1.13.1/dev/contributor/compiled_code.html)
- [PyO3 performance and interpreter detachment](https://pyo3.rs/main/performance.html)
- [PyO3 ABI features](https://pyo3.rs/main/features)
- [maturin wheel distribution](https://www.maturin.rs/distribution.html)
- [Rust NumPy bindings](https://docs.rs/numpy/latest/numpy/)
- [pybind11 NumPy support](https://pybind11.readthedocs.io/en/stable/advanced/pycpp/numpy.html)
- [Python Packaging User Guide on binary wheels](https://packaging.python.org/en/latest/flow/)
- [cibuildwheel platform matrix](https://cibuildwheel.pypa.io/en/stable/)

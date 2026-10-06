# Native-code assessment

**Recommendation:** do not add a C++ or Rust extension. Implement
deterministic algorithms in clear Python over vectorized NumPy and SciPy, use
Numba for a measured custom loop those libraries cannot express, and reassess
only from end-to-end profiles. Hebog does not depend on Numba today; add it
with the first profiled kernel that needs it.

This is a deferral with explicit gates, not a ban. If an extension becomes
justified, prefer Rust for a new self-contained kernel and C++ when
integrating a mature C/C++ library or when a C++ implementation has a clear
evidence-backed ecosystem or team advantage.

## Why the gate is closed

The [performance profile](../reference/performance-profile.md) is flat: the
largest stage is about a fifth of a run and the largest single kernel,
`fit_compact_gaussian_mixture`, is 5 to 8%, already a compiled SciPy solve.
Nothing reaches gate 1 below in one size regime, let alone two. Every
bottleneck found so far was redundant work (a scan per label, a plane decoded
per sixteen objects, a coordinate transform per source), which batching and
vectorisation removed and which a native rewrite would only have made faster.
Numba is not indicated either: the background refinement, the wavelet bank
and the fit are already vectorised NumPy or compiled SciPy, so no per-pixel
Python loop is material.

A native extension would also turn Hebog's universal wheel into a binary per
interpreter, operating system and CPU across Python 3.12 to 3.14 on Linux,
macOS and Windows, and at scale memory bandwidth, copies, storage throughput,
tile geometry and scheduler overhead are likelier limits than kernel speed.

## Decision gate

Consider a native prototype only when a profile on representative science
and data sizes shows one of these after vectorization, copy removal,
batching and a reviewed Numba attempt:

1. one self-contained kernel takes at least 10% of complete wall time in two
   representative size regimes;
2. the kernel prevents a frozen memory, latency, throughput or scaling gate
   from passing although orchestration and I/O are not the bottleneck; or
3. a mature native library already provides the reviewed algorithm and
   replacing it would add scientific or maintenance risk.

The prototype must then show all of the following:

- at least a twofold kernel speedup and a statistically supported
  improvement of at least 5% in complete runtime, unless it unlocks a failed
  memory or scalability gate;
- no unapproved regression at affected and adjacent performance tiers;
- identical scientific and partition-invariance results within reviewed
  tolerances;
- bounded, preferably zero-copy array exchange with explicit dtype, shape,
  stride, alignment, ownership and mutability;
- release of the interpreter during long native work and no thread
  oversubscription inside Dask workers;
- deterministic exceptions, with no abort, panic across the FFI boundary,
  undefined behaviour, leak or data race;
- prebuilt tested wheels for every supported platform and Python ABI, a
  verified source distribution and a fallback policy; and
- a small typed Python wrapper, the retained readable serial oracle, native
  tests, sanitizer or equivalent checks, benchmarks, provenance, licensing
  and an accepted ADR.

Measure cold import and start-up cost as well as warm execution. The
boundary operates on coarse tile arrays or bounded summaries, never on
pixels, sources or Python objects.

## Candidates and non-candidates

Possible candidates are irregular loops NumPy and SciPy cannot express:
connected-label and boundary reconciliation, deblending or watershed logic
when SciPy's semantics do not satisfy the contract, adaptive masked window
statistics if Numba misses a budget, and variable-size island reductions
dominated by Python dispatch after batching.

Not candidates: FITS, WCS, catalogue, configuration, schema, workflow and
Dask orchestration; convolution, interpolation, labelling, optimization and
FFT operations already meeting their gates through NumPy or SciPy; I/O- or
bandwidth-bound work; and small-input paths where extension import and
dispatch overhead is material.

## Rust and C++

| Criterion | Rust with PyO3/maturin | C++ with pybind11 | Hebog implication |
| --- | --- | --- | --- |
| Memory and thread safety | Strong safe-language defaults; unsafe code remains possible and must be isolated | Manual lifetime, aliasing, and race safety; mature RAII helps | Rust is preferable for new concurrent or ownership-heavy kernels |
| NumPy exchange | `rust-numpy` provides typed read-only/read-write array borrows and ndarray views | pybind11 provides mature buffer and `py::array_t` support, including shape and stride access | Both can avoid copies when the boundary contract is explicit |
| Parallel work | PyO3 supports detaching from Python; Rayon is available | pybind11 supports explicit GIL release; OpenMP/TBB and mature C++ threading are available | Either must release Python and obey Hebog/Dask thread budgets |
| Scientific ecosystem | Growing, but fewer mature astronomy and numerical libraries | Broad, mature numerical ecosystem and easier reuse of existing C/C++ code | C++ wins for an existing trusted library; do not rewrite it solely to use Rust |
| Packaging | maturin supports platform wheels, manylinux checks, and stable-ABI builds where compatible | Mature Python build and wheel tooling, usually through CMake/Meson and cibuildwheel | Both add binary release infrastructure; prove the complete wheel matrix first |
| Maintainability | Compiler-enforced ownership improves long-term safety, but adds Rust expertise and FFI concepts | More contributors may know C++, but memory safety and toolchain complexity raise review cost | Team capability and operational ownership are mandatory selection evidence |

Neither binding makes zero-copy parallelism automatic. `rust-numpy`'s safe
array borrows are not `Send` or `Sync`, so a Rayon prototype must prove its
ownership design; pybind11's `py::array_t` can force-cast a non-conforming
input and copy it, which Hebog must reject or budget. The stable ABI is not
automatic either: NumPy-facing code must prove its binding and ABI
combination supports Hebog's Python and NumPy matrix.

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

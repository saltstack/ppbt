0.2.0
=====
- Cross toolchains are now shipped as separate PyPI packages:
  ``ppbt-cross-aarch64-linux-gnu`` (aarch64 target, runs on x86_64 host)
  and ``ppbt-cross-x86_64-linux-gnu`` (x86_64 target, runs on aarch64).
  The base ``ppbt`` wheel stays lean (native toolchain only), and
  cross-compile users opt in via extras:
  ``pip install ppbt[cross-aarch64-linux-gnu]`` /
  ``pip install ppbt[cross-x86_64-linux-gnu]`` /
  ``pip install ppbt[cross-all]``.  Cross packages register themselves
  via the ``ppbt.toolchains`` entry point so base ``ppbt`` discovers
  them at import time.
- New public API: ``ppbt.archive_for(triplet)``,
  ``ppbt.toolchain_for(triplet)``, ``ppbt.available_triplets()``.
  ``ppbt.extract()`` and ``ppbt.environ()`` grow a ``triplet=`` kwarg
  defaulting to the host triplet for backward compatibility.
- Editable installs (``pip install -e``) now skip the full
  crosstool-ng build, so developers can iterate on ppbt without
  spending an hour per install.


0.1.8
=====
- Refactor to support early import of ppbt.common at relenv runtime.


0.1.7
=====
- Use tar instead of tarfile to create toolchain tarballs


0.1.6
=====

This is the release of ppbt. ppbt provides a gnu toolchain that can be used to
build c extensions for python packages. This first version uses glibc 2.17 for
maximum portability.

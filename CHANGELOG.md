0.2.0
=====
- Ship cross toolchains alongside the native one.  Each wheel now builds
  every ``<triplet>-ct-ng.config`` under ``src/ppbt/_config/<host>/``:
  the x86_64 wheel carries both ``x86_64-linux-gnu.tar.xz`` and
  ``aarch64-linux-gnu.tar.xz``, and the aarch64 wheel carries both in
  reverse.  Lets downstream tools (relenv) cross-compile for the "other"
  Linux arch without having to build a cross toolchain themselves --
  previously a multi-hour crosstool-ng build per target.
- New public helpers in ``ppbt.common`` (also re-exported from
  ``ppbt``): ``archive_for(triplet)``, ``toolchain_for(triplet)``,
  ``available_triplets()``.  ``extract()`` and ``environ()`` grow a
  ``triplet=`` kwarg that defaults to the host for backward
  compatibility.


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

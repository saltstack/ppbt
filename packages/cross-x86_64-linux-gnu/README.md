# ppbt-cross-x86_64-linux-gnu

Cross-toolchain plugin for [ppbt](https://github.com/saltstack/ppbt).

Ships a crosstool-ng-built GCC targeting `x86_64-linux-gnu` whose
driver binaries run on an `aarch64` host.  Installed as an optional
extra of the base `ppbt` package:

```
pip install ppbt[cross-x86_64-linux-gnu]
```

Discovered at runtime by base `ppbt` via the `ppbt.toolchains` entry
point:

```python
import ppbt
print(ppbt.available_triplets())
env = ppbt.environ(triplet="x86_64-linux-gnu", auto_extract=True)
```

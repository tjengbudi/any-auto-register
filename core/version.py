"""应用版本号。

CI 在构建 release 时会用 `__version__ = "<tag>"` 覆盖此文件，
本地开发时这里是 "dev" 占位。

Application version number.

CI overwrites this file with `__version__ = "<tag>"` when building a release;
locally it's just the "dev" placeholder.
"""
__version__ = "dev"

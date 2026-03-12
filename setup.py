from setuptools import setup

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:  # pragma: no cover
    _bdist_wheel = None

cmdclass = {}
if _bdist_wheel is not None:

    class PlatformWheel(_bdist_wheel):
        def finalize_options(self) -> None:
            super().finalize_options()
            self.root_is_pure = False

        def get_tag(self) -> tuple[str, str, str]:
            _python, _abi, platform_tag = super().get_tag()
            return ("py3", "none", platform_tag)

    cmdclass["bdist_wheel"] = PlatformWheel

setup(cmdclass=cmdclass)

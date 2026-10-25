"""Validate product display versions; no release-number allocation or file mutation."""
from dataclasses import dataclass
import re

_VERSION = re.compile(r'(?P<year>[0-9]{2})\.(?P<release>[1-9][0-9]*)(?:\.(?P<hotfix>[1-9][0-9]*))?(?:-(?P<stage>snapshot|pre|rc)-(?P<sequence>[1-9][0-9]*))?\Z')


@dataclass(frozen=True)
class ProductVersion:
    display: str
    year: str
    release: int
    hotfix: int | None
    stage: str | None
    sequence: int | None

    def semver_for_toolchain(self):
        """Explicit internal mapping only; display always retains the product format."""
        base = f'{int(self.year)}.{self.release}.{self.hotfix or 0}'
        return base if self.stage is None else f'{base}-{self.stage}.{self.sequence}'


def parse_public_version(value):
    match = _VERSION.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError('invalid_public_version')
    fields = match.groupdict()
    return ProductVersion(value, fields['year'], int(fields['release']),
                          int(fields['hotfix']) if fields['hotfix'] else None,
                          fields['stage'], int(fields['sequence']) if fields['sequence'] else None)


def component_manifest(version, component, sha256):
    """Only for an actually built artifact; caller must obtain approved version first."""
    parsed = parse_public_version(version)
    if component not in ('launcher', 'server', 'client', 'gm'):
        raise ValueError('invalid_component')
    if not isinstance(sha256, str) or re.fullmatch(r'[0-9a-f]{64}', sha256) is None:
        raise ValueError('invalid_artifact_sha256')
    return {'product': 'Mrad Max', 'component': component, 'version': parsed.display,
            'toolchainSemver': parsed.semver_for_toolchain(), 'sha256': sha256}

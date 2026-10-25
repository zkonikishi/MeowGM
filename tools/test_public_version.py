import unittest
from public_version import component_manifest, parse_public_version


class VersionTests(unittest.TestCase):
    def test_release_and_hotfix_display_differ_from_internal_semver(self):
        base = parse_public_version('26.1')
        self.assertEqual(base.display, '26.1')
        self.assertEqual(base.semver_for_toolchain(), '26.1.0')
        self.assertEqual(parse_public_version('26.1.2').semver_for_toolchain(), '26.1.2')

    def test_target_stage_sequence(self):
        for stage in ('snapshot', 'pre', 'rc'):
            parsed = parse_public_version(f'26.2-{stage}-3')
            self.assertEqual((parsed.release, parsed.sequence), (2, 3))
            self.assertEqual(parsed.semver_for_toolchain(), f'26.2.0-{stage}.3')

    def test_reject_old_and_ambiguous_formats(self):
        for value in (None, '', '1.0.0', '26.1.0', '26.01', '26.1-snapshot-0',
                      '26.1-beta-1', '26.1-alpha-1', '26.1-rc.1', '26.1\n', ' 26.1', '２６.1'):
            with self.assertRaises(ValueError): parse_public_version(value)

    def test_manifest_requires_real_version_and_sha(self):
        manifest = component_manifest('26.2-pre-1', 'gm', 'a' * 64)
        self.assertEqual(manifest['version'], '26.2-pre-1')
        self.assertEqual(manifest['toolchainSemver'], '26.2.0-pre.1')
        with self.assertRaises(ValueError): component_manifest(None, 'gm', 'a' * 64)
        with self.assertRaises(ValueError): component_manifest('26.2', 'gm', 'unknown')

    def test_components_share_format_without_allocating_numbers(self):
        for component in ('launcher', 'server', 'client', 'gm'):
            self.assertEqual(component_manifest('26.2-rc-1', component, 'b' * 64)['version'], '26.2-rc-1')

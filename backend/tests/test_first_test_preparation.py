"""Configuration-only regressions: no real .env or NASA access."""
import pytest
from scripts.prepare_first_harmony_test import listed_browse_layers, prepare_config


def test_prepare_mode_preserves_all_secret_bytes(tmp_path):
    path = tmp_path/'.env'
    original = (b'# Private config\r\nEDL_USERNAME=FAKE_USER\r\nEDL_PASSWORD="FAKE_COMPLEX=# abc"\r\n'
                b'EARTHDATA_TOKEN=FAKE_TOKEN\r\nHARMONY_PROCESSING_ENABLED=false\r\n'
                b'export HARMONY_AUTH_MODE = earthdata_token # old mode\r\nOTHER_SETTING=retained\r\n')
    path.write_bytes(original)
    report = prepare_config(path)
    assert path.read_bytes() == original.replace(b'export HARMONY_AUTH_MODE = earthdata_token # old mode',
                                                b'HARMONY_AUTH_MODE=earthdata_password')
    assert report['credentials_preserved'] and not report['processing_enabled']
    assert prepare_config(path)['selector_changed'] is False


def test_append_selector_preserves_existing_bytes(tmp_path):
    path = tmp_path/'.env'
    original = b'EDL_USERNAME=FAKE_USER\nEDL_PASSWORD=FAKE_PASS\nHARMONY_PROCESSING_ENABLED=false'
    path.write_bytes(original)
    prepare_config(path)
    assert path.read_bytes() == original+b'\nHARMONY_AUTH_MODE=earthdata_password\n'


@pytest.mark.parametrize('config', [
    'EDL_USERNAME=FAKE_USER\nEDL_PASSWORD=FAKE_PASS\nHARMONY_PROCESSING_ENABLED=true\n',
    'EDL_USERNAME=FAKE_USER\nHARMONY_PROCESSING_ENABLED=false\n',
    'EDL_PASSWORD=FAKE_PASS\nHARMONY_PROCESSING_ENABLED=false\n',
    'EDL_USERNAME=FAKE_USER\nEDL_PASSWORD=FAKE_PASS\n',
])
def test_unsafe_or_missing_configuration_never_written(tmp_path,config):
    path = tmp_path/'.env'
    path.write_text(config)
    before = path.read_bytes()
    with pytest.raises(RuntimeError):
        prepare_config(path)
    assert path.read_bytes() == before


def test_actual_asf_browse_naming_does_not_confuse_frequency_b_or_downloads():
    umm = {'RelatedUrls':[
        {'Type':'GET RELATED VISUALIZATION','URL':'https://example.test/SCENE_NATIVE_A_HHHH.png?private=value'},
        {'Type':'GET RELATED VISUALIZATION','URL':'https://example.test/SCENE_NATIVE_B_HHHH.png'},
        {'Type':'GET DATA','URL':'https://example.test/UNRELATED_NATIVE_A_HHHH.png'},
    ]}
    assert listed_browse_layers(umm) == ['SCENE_NATIVE_A_HHHH.png']

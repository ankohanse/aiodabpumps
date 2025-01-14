import asyncio
import copy
import logging
import pytest
import pytest_asyncio

from aiodabpumps import (
    DabPumpsApi,
    DabPumpsInstall,
    DabPumpsDevice,
    DabPumpsConfig,
    DabPumpsParams,
    DabPumpsStatus,
    DabPumpsApiAuthError,
    DabPumpsApiRightsError, 
    DabPumpsApiError, 
    DabPumpsApiHistoryItem, 
    DabPumpsApiHistoryDetail,
)

from . import TEST_USERNAME, TEST_PASSWORD

_LOGGER = logging.getLogger(__name__)


class TestContext:
    def __init__(self):
        self.api = None

    async def cleanup(self):
        if self.api:
            await self.api.async_logout()
            await self.api.async_close()


@pytest_asyncio.fixture
async def context():
    # Prepare
    ctx = TestContext()

    # pass objects to tests
    yield ctx

    # cleanup
    await ctx.cleanup()

@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, usr, pwd, exp_except",
    [
        ("login ok",   TEST_USERNAME, TEST_PASSWORD, None),
        ("login fail", "dummy_usr",   "wrong_pwd",   DabPumpsApiAuthError),
    ]
)
async def test_login(name, usr, pwd, exp_except, request):
    context = request.getfixturevalue("context")
    assert context.api is None

    context.api = DabPumpsApi(usr, pwd)

    if exp_except is None:
        assert context.api.login_method is None

        await context.api.async_login()

        assert context.api.login_method is not None
        assert context.api.install_map is not None
        assert context.api.device_map is not None
        assert context.api.config_map is not None
        assert context.api.status_map is not None
        assert context.api.string_map is not None
        assert len(context.api.install_map) == 0
        assert len(context.api.device_map) == 0
        assert len(context.api.config_map) == 0
        assert len(context.api.status_map) == 0
        assert len(context.api.string_map) == 0

    else:
        with pytest.raises(exp_except):
            await context.api.async_login()


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, exp_except",
    [
        ("data ok", None),
    ]
)
async def test_get_data(name, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = DabPumpsApi(TEST_USERNAME, TEST_PASSWORD)

    # Login
    await context.api.async_login()

    # Get install list
    await context.api.async_fetch_install_list()

    assert context.api.install_map is not None
    assert type(context.api.install_map) is dict
    assert len(context.api.install_map) > 0

    for install_id,install in context.api.install_map.items():
        assert type(install_id) is str
        assert type(install) is DabPumpsInstall
        assert install.id is not None    
        assert install.name is not None  

    # Get install details
    await context.api.async_fetch_install_details(install_id)

    assert context.api.device_map is not None
    assert type(context.api.device_map) is dict
    assert len(context.api.device_map) > 0

    for device_serial,device in context.api.device_map.items():
        assert type(device_serial) is str
        assert type(device) is DabPumpsDevice
        assert device.id is not None    
        assert device.serial is not None    
        assert device.name is not None  
        assert device.config_id is not None  
        assert device.install_id is not None  

    # Get device details
    await context.api.async_fetch_device_details(device.serial)
    device = context.api.device_map[device.serial]  # device properties have now refreshed
    assert device.sw_version is not None

    # Get device config
    await context.api.async_fetch_device_config(device.config_id)

    assert context.api.config_map is not None
    assert type(context.api.config_map) is dict
    assert len(context.api.config_map) > 0

    for config_id,config in context.api.config_map.items():
        assert type(config_id) is str
        assert type(config) is DabPumpsConfig
        assert config.id is not None
        assert config.label is not None

        assert config.meta_params is not None
        assert type(config.meta_params) is dict
        assert len(config.meta_params) > 0

        for param_name,param in config.meta_params.items():
            assert type(param_name) is str
            assert type(param) is DabPumpsParams
            assert param.key is not None

    # Get device statusses
    await context.api.async_fetch_device_statusses(device_serial)

    assert context.api.status_map is not None
    assert type(context.api.status_map) is dict
    assert len(context.api.status_map) > 0

    for status_id,status in context.api.status_map.items():
        assert type(status_id) is str
        assert type(status) is DabPumpsStatus
        assert status.serial is not None
        assert status.key is not None


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, key, val, exp_except",
    [
        ("set PowerShowerBoost 30", "PowerShowerBoost", "30", None),
        ("set PowerShowerBoost 20", "PowerShowerBoost", "20", None),
        ("set PowerShowerDuration 360", "PowerShowerDuration", "360", None),
        ("set PowerShowerDuration 300", "PowerShowerDuration", "300", None),
        ("set SleepModeEnable on", "SleepModeEnable", "1", None),
        ("set SleepModeEnable off", "SleepModeEnable", "0", None),
    ]
)
async def test_set_data(name, key, val, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = DabPumpsApi(TEST_USERNAME, TEST_PASSWORD)

    # Login
    await context.api.async_login()

    # Get install list
    await context.api.async_fetch_install_list()

    assert context.api.install_map is not None
    assert type(context.api.install_map) is dict
    assert len(context.api.install_map) > 0

    # Get install details
    for install_id in context.api.install_map:
        await context.api.async_fetch_install_details(install_id)

    # Get device statusses
    for device_serial in context.api.device_map:
        await context.api.async_fetch_device_statusses(device_serial)

    status = next( (status for status in context.api.status_map.values() if status.key==key), None)
    assert status is not None

    changed = await context.api.async_change_device_status(status.serial, status.key, val)

    # Do immediate test of changed value. 
    # We hold the changed value while the backend is processing the change.
    if changed:
        await context.api.async_fetch_device_statusses(status.serial)

        status = next( (status for status in context.api.status_map.values() if status.key==key), None)
        assert status.val == val
        assert status.update_ts is not None

        # Wait until the backend has processed the change and test again
        await asyncio.sleep(30)

    # Test (either not changed or after change has been processed by backend)
    await context.api.async_fetch_device_statusses(status.serial)

    status = next( (status for status in context.api.status_map.values() if status.key==key), None)
    assert status.val == val
    assert status.update_ts is None


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, lang, exp_lang",
    [
        ("strings en", 'en', 'en'),
        ("strings nl", 'nl', 'nl'),
        ("strings xx", 'xx', 'en'),
    ]
)
async def test_strings(name, lang, exp_lang, request):
    context = request.getfixturevalue("context")
    context.api = DabPumpsApi("dummy_usr", "wrong_pwd") # no login needed

    # Get strings
    await context.api.async_fetch_strings(lang)

    assert context.api.string_map is not None
    assert type(context.api.string_map) is dict
    assert len(context.api.string_map) > 0

    assert context.api.string_map_lang == exp_lang

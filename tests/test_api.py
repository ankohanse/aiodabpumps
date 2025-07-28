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

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class TestContext:
    def __init__(self):
        self.api = None

    async def cleanup(self):
        if self.api:
            await self.api.async_logout()
            await self.api.async_close()
            assert self.api.closed == True


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
    assert context.api.closed == False

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
    "name, usr, pwd, exp_except",
    [
        ("login multi", TEST_USERNAME, TEST_PASSWORD, None),
    ]
)
async def test_login_seq(name, usr, pwd, exp_except, request):
    context = request.getfixturevalue("context")
    assert context.api is None

    # First call with wrong pwd
    context.api = DabPumpsApi(usr, pwd+"xxx")
    assert context.api.closed == False
    assert context.api.login_method is None

    with pytest.raises(DabPumpsApiAuthError):
        await context.api.async_login()

    # Next call with correct pwd
    context.api = DabPumpsApi(usr, pwd)
    assert context.api.closed == False
    assert context.api.login_method is None

    if exp_except is None:
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
    "name, loop, exp_except",
    [
        ("data ok", 0, None),
        # ("data loop", 24*60, None),    # Run 1 full day
    ]
)
async def test_get_data(name, loop, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = DabPumpsApi(TEST_USERNAME, TEST_PASSWORD)
    assert context.api.closed == False

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

    # Get install details (just for the first install)
    await context.api.async_fetch_install(install_id)

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
        assert device.sw_version is not None

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

    counter_success: int = 0
    counter_fail: int = 0
    reason_fail: dict[str,int] = {}
    for idx in range(1,loop+1):
        # Get device statusses
        try:
            # Check cookie and re-login if needed
            await context.api.async_login()

            for device_serial,device in context.api.device_map.items():
                await context.api.async_fetch_device_statusses(device_serial)

            assert context.api.status_map is not None
            assert type(context.api.status_map) is dict
            assert len(context.api.status_map) > 0

            for status_id,status in context.api.status_map.items():
                assert type(status_id) is str
                assert type(status) is DabPumpsStatus
                assert status.serial is not None
                assert status.key is not None
                assert status.name is not None

            counter_success += 1
        
        except Exception as ex:
            counter_fail += 1
            reason = str(ex)
            reason_fail[reason] = reason_fail[reason]+1 if reason in reason_fail else 1
            _LOGGER.warning(f"Fail: {ex}")

        if loop:
            await asyncio.sleep(60)
            _LOGGER.debug(f"Loop test, {idx} of {loop} (success={counter_success}, fail={counter_fail})")

    _LOGGER.info(f"Fail summary after {loop} loops:")
    for reason,count in reason_fail.items():
        _LOGGER.info(f"  {count}x {reason}")


@pytest.mark.asyncio
@pytest.mark.usefixtures("context")
@pytest.mark.parametrize(
    "name, key, code, exp_code, exp_except",
    [
        ("set PowerShowerBoost 30", "PowerShowerBoost", "30", "30", None),
        ("set PowerShowerBoost 20", "PowerShowerBoost", "20", "20", None),
        ("set PowerShowerDuration 360", "PowerShowerDuration", "360", "360", None),
        ("set PowerShowerDuration 300", "PowerShowerDuration", "300", "300", None),
        ("set SleepModeEnable on", "SleepModeEnable", "1", "1", None),
        ("set SleepModeEnable off", "SleepModeEnable", "0", "0", None),
        ("set RF_EraseHistoricalFault", "RF_EraseHistoricalFault", "1", "0", None), # Falls back to 0 after STATUS_UPDATE_HOLD
    ]
)
async def test_set_data(name, key, code, exp_code, exp_except, request):
    context = request.getfixturevalue("context")
    context.api = DabPumpsApi(TEST_USERNAME, TEST_PASSWORD)
    assert context.api.closed == False

    # Login
    await context.api.async_login()

    # Get install list
    await context.api.async_fetch_install_list()

    assert context.api.install_map is not None
    assert type(context.api.install_map) is dict
    assert len(context.api.install_map) > 0

    # Get install details and metadata
    for install_id in context.api.install_map:
        await context.api.async_fetch_install(install_id)

    # Get device statusses
    for device_serial in context.api.device_map:
        await context.api.async_fetch_device_statusses(device_serial)

    status = next( (status for status in context.api.status_map.values() if status.key==key), None)
    assert status is not None

    changed = await context.api.async_change_device_status(status.serial, status.key, code=code)

    # Do immediate test of changed value. 
    # We hold the changed value while the backend is processing the change.
    if changed:
        await context.api.async_fetch_device_statusses(status.serial)

        status = next( (status for status in context.api.status_map.values() if status.key==key), None)
        assert status.code == code
        assert status.update_ts is not None

        # Wait until the backend has processed the change and test again
        await asyncio.sleep(40)

    # Test (either not changed or after change has been processed by backend)
    await context.api.async_fetch_device_statusses(status.serial)

    status = next( (status for status in context.api.status_map.values() if status.key==key), None)
    assert status.code == exp_code
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


@pytest.mark.parametrize(
    "name, attr, exp_id",
    [
        ("multi", ['abc', 'DEF', '123'], 'abc_def_123'),
        ("spaces", ['abc DEF', '123'], 'abc_def_123'),
        ("underscore", ['abc_DEF', '123'], 'abc_def_123'),
        ('ignored start', ['@%^_DEF', '123'], '_def_123'),
        ('ignored mid', ['@bc_DE#', '123'], 'bc_de_123'),
        ('ignored end', ['abc_DEF', '!&'], 'abc_def_'),
    ]
)
def test_create_id(name, attr, exp_id, request):

    id = DabPumpsApi.create_id(*attr)
    assert id == exp_id


@pytest_asyncio.fixture
async def device_map():
    device_map = {
        "SERIAL": DabPumpsDevice(
            vendor = 'DAB Pumps',
            name = 'test device',
            id = DabPumpsApi.create_id('test device'),
            serial = 'SERIAL',
            product = 'test product',
            hw_version = 'test hw version',
            config_id = 'CONFIG_ID',
            install_id = 'INSTALL_ID',
            sw_version = 'test sw version',
            mac_address = 'test mac',
        ),
    }
    yield device_map

@pytest_asyncio.fixture
async def config_map():
    config_map = {
        "CONFIG_ID": DabPumpsConfig(
            id = 'CONFIG_ID',
            label = 'test label',
            description = 'test description',
            meta_params = {
                "KEY_ENUM":  DabPumpsParams(key='KEY_ENUM',  type='enum',    unit=None, weight=None, values={'1':'one', '2':'two', '3':'three'}, min=1, max=3, family='f', group='g', view='CSIR', change='', log='', report=''),
                "KEY_FLOAT": DabPumpsParams(key='KEY_FLOAT', type='measure', unit='F',  weight=0.1,  values=None, min=0, max=1,  family='f', group='g', view='CSIR', change='', log='', report=''),
                "KEY_INT":   DabPumpsParams(key='KEY_INT',   type='measure', unit='I',  weight=1,    values=None, min=0, max=10, family='f', group='g', view='CSIR', change='', log='', report=''),
                "KEY_LABEL": DabPumpsParams(key='KEY_LABEL', type='label',   unit='',   weight=None, values=None, min=0, max=0,  family='f', group='g', view='CSIR', change='', log='', report=''),
            }
        ),
    }
    yield config_map

@pytest_asyncio.fixture
async def status_map():
    status_map = {
        'serial_key_enum': DabPumpsStatus('SERIAL', 'KEY_ENUM', 'NameEnum', '1', 'one', None, None, None),
        'serial_key_float': DabPumpsStatus('SERIAL', 'KEY_FLOAT', 'NameFloat', '1', 0.1, 'F', None, None),
        'serial_key_int': DabPumpsStatus('SERIAL', 'KEY_INT', 'NameInt', '1', 1, 'I', None, None),
        'serial_key_label': DabPumpsStatus('SERIAL', 'KEY_LABEL', 'NameLabel', 'ABC', 'ABC', None, None, None),
    }
    yield status_map

@pytest_asyncio.fixture
async def string_map():
    string_map = {
        'one': 'een',
        'two': 'twee',
        'three': 'drie',
        'ABC': 'aa bee cee',
    }
    yield string_map


@pytest.mark.asyncio
@pytest.mark.usefixtures("context", "device_map", "config_map", "string_map")
@pytest.mark.parametrize(
    "name, serial, key, translate, code, exp_value",
    [
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', True, '2', ('2', '')),
        ("key unknown", 'SERIAL', 'KEY_XX', True, '2', ('2', '')),
        ("enum ok", "SERIAL", 'KEY_ENUM', False, '2', ('two', None)),
        ("enum ok", "SERIAL", 'KEY_ENUM', True, '2', ('twee', None)),
        ("enum no", "SERIAL", 'KEY_ENUM', False, '4', ('4', None)),
        ("enum no", "SERIAL", 'KEY_ENUM', True, '4', ('4', None)),
        ("float ok", "SERIAL", 'KEY_FLOAT', True, '2', (0.2, 'F')),
        ("float min", "SERIAL", 'KEY_FLOAT', True, '-1', (-0.1, 'F')),
        ("float max", "SERIAL", 'KEY_FLOAT', True, '11', (1.1, 'F')),
        ("int ok", "SERIAL", 'KEY_INT', True, '2', (2, 'I')),
        ("int min", "SERIAL", 'KEY_INT', True, '-1', (-1, 'I')),
        ("int max", "SERIAL", 'KEY_INT', True, '11', (11, 'I')),
        ("label ok", "SERIAL", 'KEY_LABEL', True, 'ABC', ('ABC', '')),
    ]
)
async def test_decode(name, serial, key, translate, code, exp_value, request):
    context = request.getfixturevalue("context")
    context.api = DabPumpsApi("dummy_usr", "wrong_pwd") # no login needed

    context.api._device_map = request.getfixturevalue("device_map")
    context.api._config_map = request.getfixturevalue("config_map")
    if translate:
        context.api._string_map = request.getfixturevalue("string_map")

    value = context.api._decode_status_value(serial, key, code)
    assert value == exp_value
    assert type(value) == type(exp_value)


@pytest.mark.asyncio
@pytest.mark.usefixtures("context", "device_map", "config_map")
@pytest.mark.parametrize(
    "name, serial, key, value, exp_code",
    [
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', 'two', 'two'),
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', 'two', 'two'),
        ("key unknown", 'SERIAL', 'KEY_XX', 'two', 'two'),
        ("enum ok", "SERIAL", 'KEY_ENUM', 'two', '2'),
        ("enum no", "SERIAL", 'KEY_ENUM', 'four', 'four'),
        ("float ok", "SERIAL", 'KEY_FLOAT', 0.2, '2'),
        ("float min", "SERIAL", 'KEY_FLOAT', -0.1, '-1'),
        ("float max", "SERIAL", 'KEY_FLOAT', 1.1, '11'),
        ("int ok", "SERIAL", 'KEY_INT', 2, '2'),
        ("int min", "SERIAL", 'KEY_INT', -1, '-1'),
        ("int max", "SERIAL", 'KEY_INT', 11, '11'),
        ("label ok", "SERIAL", 'KEY_LABEL', 'ABC', 'ABC'),
    ]
)
async def test_encode(name, serial, key, value, exp_code, request):
    context = request.getfixturevalue("context")
    context.api = DabPumpsApi("dummy_usr", "wrong_pwd") # no login needed

    context.api._device_map = request.getfixturevalue("device_map")
    context.api._config_map = request.getfixturevalue("config_map")

    code = context.api._encode_status_value(serial, key, value)
    assert code == exp_code
    assert type(code) == type(exp_code)


@pytest.mark.asyncio
@pytest.mark.usefixtures("context", "device_map", "config_map", "status_map", "string_map")
@pytest.mark.parametrize(
    "name, serial, key, exp_code, exp_value, exp_unit",
    [
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', None, None, None),
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', None, None, None),
        ("key unknown", 'SERIAL', 'KEY_XX', None, None, None),
        ("enum ok", "SERIAL", 'KEY_ENUM', '1', 'one', None),
        ("float ok", "SERIAL", 'KEY_FLOAT', '1', 0.1, 'F'),
        ("int ok", "SERIAL", 'KEY_INT', '1', 1, 'I'),
        ("label ok", "SERIAL", 'KEY_LABEL', 'ABC', 'ABC', None),
    ]
)
async def test_status(name, serial, key, exp_code, exp_value, exp_unit, request):
    context = request.getfixturevalue("context")
    context.api = DabPumpsApi("dummy_usr", "wrong_pwd") # no login needed

    context.api._device_map = request.getfixturevalue("device_map")
    context.api._config_map = request.getfixturevalue("config_map")
    context.api._status_actual_map = request.getfixturevalue("status_map")
    context.api._status_static_map = {}
    context.api._string_map = request.getfixturevalue("string_map")

    status = context.api.get_status_value(serial, key)
    if exp_code is None:
        assert status is None
    else:
        assert status is not None
        assert status.serial == serial
        assert status.key == key
        assert status.code == exp_code
        assert status.value == exp_value
        assert status.unit == exp_unit


@pytest.mark.asyncio
@pytest.mark.usefixtures("context", "device_map", "config_map", "status_map", "string_map")
@pytest.mark.parametrize(
    "name, serial, key, translate, exp_type, exp_values, exp_unit",
    [
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', False, None, None, None),
        ("device unknown", 'SERIAL_XX', 'KEY_ENUM', False, None, None, None),
        ("key unknown", 'SERIAL', 'KEY_XX', False, None, None, None),
        ("enum ok", "SERIAL", 'KEY_ENUM', False, 'enum', {'1':'one', '2':'two', '3':'three'}, None),
        ("enum ok", "SERIAL", 'KEY_ENUM', True, 'enum', {'1':'een', '2':'twee', '3':'drie'}, None),
        ("float ok", "SERIAL", 'KEY_FLOAT', False, 'measure', None, 'F'),
        ("int ok", "SERIAL", 'KEY_INT', False, 'measure', None, 'I'),
        ("label ok", "SERIAL", 'KEY_LABEL', False, 'label', None, ''),
    ]
)
async def test_metadata(name, serial, key, translate, exp_type, exp_values, exp_unit, request):
    context = request.getfixturevalue("context")
    context.api = DabPumpsApi("dummy_usr", "wrong_pwd") # no login needed

    context.api._device_map = request.getfixturevalue("device_map")
    context.api._config_map = request.getfixturevalue("config_map")
    context.api._status_actual_map = request.getfixturevalue("status_map")
    context.api._status_static_map = {}
    context.api._string_map = request.getfixturevalue("string_map")

    params = context.api.get_status_metadata(serial, key, translate=translate)
    if exp_type is None:
        assert params is None
    else:
        assert params is not None
        assert params.key == key
        assert params.type == exp_type
        assert params.unit == exp_unit

        if exp_values is None:
            assert params.values is None
        else:
            assert params.values is not None
            assert len(params.values) == len(exp_values)
            for k,v in exp_values.items():
                assert k in params.values
                assert params.values[k] == v

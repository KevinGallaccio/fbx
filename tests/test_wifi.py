"""`fbx wifi` — state, config, APs, BSS, stations against captured/live shapes."""

from __future__ import annotations

import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import authorize, mock_get, mock_login

runner = CliRunner()

STATE = {
    "state": "enabled",
    "power_saving_capability": "supported",
    "expected_phys": [
        {"band": "2d4g", "phy_id": 0, "detected": True},
        {"band": "5g", "phy_id": 1, "detected": True},
        {"band": "5g", "phy_id": 10, "detected": True},
        {"band": "6g", "phy_id": 11, "detected": True},
    ],
}

CONFIG = {"enabled": True, "power_saving": False, "mac_filter_state": "disabled"}

APS = [
    {
        "id": 0,
        "name": "2.4G",
        "config": {
            "enabled": True,
            "band": "2d4g",
            "channel_width": "20",
            "primary_channel": 0,
            "secondary_channel": 0,
            "dfs_enabled": False,
        },
        "status": {
            "state": "active",
            "primary_channel": 6,
            "secondary_channel": 0,
            "channel_width": "20",
            "dfs_disabled": False,
        },
    },
    {
        "id": 11,
        "name": "6G",
        "config": {
            "enabled": True,
            "band": "6g",
            "channel_width": "320",
            "primary_channel": 0,
            "secondary_channel": 0,
            "dfs_enabled": True,
        },
        "status": {
            "state": "active",
            "primary_channel": 85,
            "secondary_channel": 0,
            "channel_width": "320",
            "dfs_disabled": False,
        },
    },
]

BSS = [
    {
        "id": "02:00:00:00:00:10",
        "phy_id": 11,
        "use_shared_params": True,
        "disable_wep": True,
        "config": {
            "enabled": True,
            "ssid": "scrubbed-ssid-1",
            "encryption": "wpa3_psk_ccmp",
            "key": "SCRUBBED_KEY",
            "hide_ssid": False,
            "eapol_version": 2,
            "gcmp256": False,
            "wps_enabled": True,
        },
        "status": {
            "state": "active",
            "band": "6G",
            "sta_count": 3,
            "authorized_sta_count": 3,
            "is_main_bss": False,
        },
    }
]

# Station shape verified live (fbxgw9-r1, firmware 4.12.2): the per-AP stations
# endpoint is inventory-only in the docs, so this fixture is our contract.
STATION_AP0 = {
    "id": "02:00:00:00:00:10-02:00:00:00:00:14",
    "mac": "02:00:00:00:00:14",
    "bssid": "02:00:00:00:00:10",
    "hostname": "host-37",
    "host": {"id": "ether-02:00:00:00:00:14", "primary_name": "host-37"},
    "state": "authenticated",
    "wpa_alg": "wpa2",
    "pairwise_cipher": "ccmp",
    "signal": -34,
    "inactive": 0,
    "conn_duration": 81267,
    "rx_bytes": 55438,
    "tx_bytes": 211431,
    "rx_rate": 87,
    "tx_rate": 13,
    "flags": {"legacy": False, "authorized": True},
}

STATION_AP11 = {
    "id": "02:00:00:00:00:11-02:00:00:00:00:15",
    "mac": "02:00:00:00:00:15",
    "bssid": "02:00:00:00:00:11",
    "hostname": "host-38",
    "state": "authenticated",
    "wpa_alg": "wpa3",
    "signal": -71,
    "conn_duration": 156,
    "rx_rate": 0,
    "tx_rate": 0,
}


@respx.mock
def test_status_table_lists_radios():
    authorize()
    mock_login()
    mock_get("wifi/state/", STATE)
    result = runner.invoke(app, ["wifi", "status"])
    assert result.exit_code == 0
    assert "6g" in result.stdout
    assert "2d4g" in result.stdout


@respx.mock
def test_config_json_is_whole_result():
    authorize()
    mock_login()
    mock_get("wifi/config/", CONFIG)
    result = runner.invoke(app, ["--json", "wifi", "config"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == CONFIG


@respx.mock
def test_ap_table_shows_wifi7_width():
    authorize()
    mock_login()
    mock_get("wifi/ap/", APS)
    result = runner.invoke(app, ["wifi", "ap"])
    assert result.exit_code == 0
    assert "320" in result.stdout  # 320 MHz = Wi-Fi 7 on the 6 GHz radio
    assert "85" in result.stdout  # live channel from status, not config


@respx.mock
def test_bss_table_never_shows_the_key():
    authorize()
    mock_login()
    mock_get("wifi/bss/", BSS)
    result = runner.invoke(app, ["wifi", "bss"])
    assert result.exit_code == 0
    assert "wpa3_psk_ccmp" in result.stdout
    assert "scrubbed-ssid-1" in result.stdout
    assert "SCRUBBED_KEY" not in result.stdout  # PSK only via --json, never in a table


@respx.mock
def test_bss_json_is_whole_result_including_key():
    authorize()
    mock_login()
    mock_get("wifi/bss/", BSS)
    result = runner.invoke(app, ["--json", "wifi", "bss"])
    assert json.loads(result.stdout) == BSS  # rule #5: never a lossy subset


@respx.mock
def test_stations_aggregates_across_aps():
    authorize()
    mock_login()
    mock_get("wifi/ap/", APS)
    mock_get("wifi/ap/0/stations/", [STATION_AP0])
    mock_get("wifi/ap/11/stations/", [STATION_AP11])
    result = runner.invoke(app, ["--json", "wifi", "stations"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 2
    by_mac = {s["mac"]: s for s in payload}
    assert by_mac["02:00:00:00:00:14"]["_fbx_ap"] == {"id": 0, "name": "2.4G", "band": "2d4g"}
    assert by_mac["02:00:00:00:00:15"]["_fbx_ap"] == {"id": 11, "name": "6G", "band": "6g"}


@respx.mock
def test_stations_table_shows_signal_and_auth():
    authorize()
    mock_login()
    mock_get("wifi/ap/", APS)
    mock_get("wifi/ap/0/stations/", [STATION_AP0])
    mock_get("wifi/ap/11/stations/", [STATION_AP11])
    result = runner.invoke(app, ["wifi", "stations"])
    assert result.exit_code == 0
    assert "host-37" in result.stdout
    assert "-34 dBm" in result.stdout
    assert "wpa3" in result.stdout


@respx.mock
def test_stations_single_ap_option():
    authorize()
    mock_login()
    ap_route = mock_get("wifi/ap/", APS)
    route = mock_get("wifi/ap/11/stations/", [STATION_AP11])
    result = runner.invoke(app, ["--json", "wifi", "stations", "--ap", "11"])
    assert result.exit_code == 0
    assert route.called
    assert not ap_route.called  # direct fetch — no AP walk
    assert json.loads(result.stdout) == [STATION_AP11]

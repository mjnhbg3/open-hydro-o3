import pytest


@pytest.mark.asyncio
async def test_database_store_and_fetch(temp_db, mock_sensor_data):
    await temp_db.init()
    rid = await temp_db.store_sensor_reading(mock_sensor_data)
    assert isinstance(rid, int)
    rows = await temp_db.get_recent_sensor_data(hours=1)
    assert rows and rows[0]["ph"] == mock_sensor_data["water"]["ph"]

    action_id = await temp_db.store_actuator_action(
        {
            "timestamp": mock_sensor_data["timestamp"],
            "executed": {"pump_a": {"ml": 2}},
            "fan_speed": 50,
        }
    )
    assert action_id
    acts = await temp_db.get_recent_actions(hours=1)
    assert acts and acts[0]["fan_speed"] == 50

    stats = await temp_db.get_database_stats()
    assert stats["sensor_readings_count"] >= 1
    await temp_db.close()


@pytest.mark.asyncio
async def test_cleanup_and_stats(temp_db, mock_sensor_data):
    await temp_db.init()
    await temp_db.store_sensor_reading(mock_sensor_data)
    await temp_db.cleanup_old_data(days_to_keep=0)
    rows = await temp_db.get_recent_sensor_data(hours=1)
    assert rows == []
    stats = await temp_db.get_database_stats()
    assert isinstance(stats, dict)


@pytest.mark.asyncio
async def test_kpi_history(temp_db, mock_sensor_data):
    await temp_db.init()
    await temp_db.store_sensor_reading(mock_sensor_data)
    await temp_db.store_kpi_rollup(
        {"timestamp": mock_sensor_data["timestamp"], "period": "daily"}
    )
    history = await temp_db.get_kpi_history(days=1)
    assert history and history[0]["period"] == "daily"

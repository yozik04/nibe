from nibe.console_scripts.convert_csv import run


async def test_verify_data_files():
    await run("verify")

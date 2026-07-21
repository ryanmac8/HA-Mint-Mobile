import asyncio
import json
import os
import pprint
import aiohttp
from api import MintMobile

pp = pprint.PrettyPrinter(indent=4)

async def main():
    username = input("Phone Number: ")
    password = input("Enter Your Password: ")

    token_file = "test_tokens.json"
    token_data = {}
    if os.path.exists(token_file):
        try:
            with open(token_file, "r") as f:
                token_data = json.load(f)
        except Exception:
            pass

    def token_update_callback(token, refresh_token, expires_at):
        with open(token_file, "w") as f:
            json.dump({
                "token": token,
                "refresh_token": refresh_token,
                "expires_at": expires_at
            }, f)
        print("[test] Cached tokens saved to test_tokens.json")

    async with aiohttp.ClientSession() as session:
        mm = MintMobile(
            session=session,
            username=username,
            password=password,
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            expires_at=token_data.get("expires_at"),
            token_update_callback=token_update_callback
        )
        
        print("Ensuring valid session...")
        if await mm.async_ensure_valid_session():
            print("Session Valid/Acquired")
        else:
            print("Failed to acquire valid session")
            return

        print("Printing All Mint Mobiles Found:")
        lines = await mm.async_lines()
        pp.pprint(lines)

        print("\nPrinting Data From All Lines:")
        data = await mm.async_get_all_data_remaining()
        pp.pprint(data)

if __name__ == "__main__":
    asyncio.run(main())

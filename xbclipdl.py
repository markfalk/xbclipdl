import hashlib
import json
import os
import time
import logging
import requests
import shutil
import subprocess
import shelve

# Set up logging
log = logging.getLogger('name')
log.setLevel(logging.DEBUG)
fh = logging.FileHandler('data/xboxclips.log')
fh.setLevel(logging.DEBUG)
log.addHandler(fh)

# Load cache from disk
cache_file = 'data/xboxclips_cache.db'
with shelve.open(cache_file) as cache:
    cache_hash = cache.get("hash", "")
    gameClipIds = cache.get("gameClipIds", [])
    counter = cache.get("counter", 0)

options = {
    "xbl.io": {
        "base_uri": "https://xbl.io/api/v2/",
        "apikey": os.environ.get("XBL_API_KEY"),
        "retries": 0
    },
    "xbox": {
        "gameClipId": ["*"]
    },
    "download": {
        "file_format": "original",
        "destination": "./data/",
        "retries": 0
    },
    "ffmpeg": {
        "bin": "/usr/local/bin/ffmpeg",
        "args": ["-i"],
        "search": "OK"
    }
}

# Downloading file list
print("Downloading file list...")
client = requests.Session()
client.headers.update({"Accept": "application/json", "X-Authorization": options["xbl.io"]["apikey"]})

retries = options["xbl.io"]["retries"]

while retries+1 > 0:
    try:
        response = client.get(f"{options['xbl.io']['base_uri']}dvr/gameclips")
        response.raise_for_status()
        gameClips = response.json().get("values")
        continuationToken = response.json().get("continuationToken")
        while continuationToken:
            response = client.get(f"{options['xbl.io']['base_uri']}dvr/gameclips?continuationToken={continuationToken}")
            response.raise_for_status()
            gameClips += response.json().get("values")
            continuationToken = response.json().get("continuationToken")
        log.info("Downloading file list")
        # if response.status_code != 200:
        #     log.error("Error calling dowload file list")
        #     log.error("Response code: %i", response.status_code)
        #     log.error("Response test: %s", response.text)
        #     log.info("Retrying")
        #     retries -= 1
        if not gameClips:
            log.error("No valid JSON")
            time.sleep(5)
            print("retrying...")
            log.info("Retrying")
            retries -= 1
        else:
            break
    except Exception as e:
        log.error(f"Error: {e}")
        time.sleep(5)
        print("retrying...")
        log.info("Retrying")
        retries -= 1

if not gameClips:
    log.error("No valid JSON")
    raise SystemExit("No valid JSON.")

gameClips.reverse()
hash_value = hashlib.md5(json.dumps([clip["contentId"] for clip in gameClips]).encode()).hexdigest()

log.info("Cache", extra={"hash": cache_hash, "gameClipIds": gameClipIds, "counter": counter})
log.info("Hash", extra={"cached": cache_hash, "hash": hash_value})

if hash_value == cache_hash:
    raise SystemExit("Nothing to update!")
else:
    with shelve.open(cache_file) as cache:
        cache["hash"] = hash_value

for gameClip in gameClips:
    if gameClip["contentId"] not in gameClipIds and (
        gameClip["titleName"] in options["xbox"]["gameClipId"]
        or "*" in options["xbox"]["gameClipId"]
    ):
        counter += 1
        retries = options["download"]["retries"]
        clipNameDateId = f"{'-'.join((gameClip['titleName'],gameClip['uploadDate'].replace(':','-').split('.')[0],gameClip['contentId'].split('-')[0]))}"
        clipNameDateId = clipNameDateId.encode("ascii", "ignore").decode()
        destination = f"{clipNameDateId}.mp4" if options["download"]["file_format"] == "original" else f"{counter}.mp4"
        uri = next(item['uri'] for item in gameClip['contentLocators'] if item['locatorType'] == 'Download')
        print(f"{gameClip['contentId']}->{destination}... uri: {uri}")
        log.info(f"{gameClip['contentId']}->{destination}... uri: {uri}")

        # Ensure download directory exists
        if not os.path.exists(options["download"]["destination"]):
            os.makedirs(options["download"]["destination"])

        if not os.path.exists(os.path.join(options["download"]["destination"], destination)):
            while retries >= 0:
                response = requests.get(uri, stream=True)
                with open(os.path.join(options["download"]["destination"], destination), "wb") as f:
                    shutil.copyfileobj(response.raw, f)

                # Verify file consistency
                # process = subprocess.run(
                #     [options["ffmpeg"]["bin"], *options["ffmpeg"]["args"], os.path.join(options["download"]["destination"], destination)],
                #     capture_output=True,
                #     text=True,
                # )
                # output = process.stdout
                # if options["ffmpeg"]["search"] in output:
                #     if os.remove(os.path.join(options["download"]["destination"], destination)):
                #         os.unlink(os.path.join(options["download"]["destination"], destination))
                #     print("error...")
                #     log.error("mp4 file inconsistent")
                #     retries -= 1
                #     print("retrying...")
                #     log.info("Retrying")
                # else:
                #     print("ok...")
                #     log.info("File downloaded")
                #     gameClipIds.append(gameClip["contentId"])
                #     break
                print("ok...")
                log.info("File downloaded")
                gameClipIds.append(gameClip["contentId"])
                break

# cache["hash"] = hash_value
# cache["gameClipIds"] = gameClipIds
# cache["counter"] = counter

# Save cache to disk
    # print("Exiting after 1...")
    # break
with shelve.open(cache_file, writeback=True) as cache:
    cache["hash"] = hash_value
    cache["gameClipIds"] = gameClipIds
    cache["counter"] = counter
    log.info("Saving Cache", extra={"hash": cache["hash"], "gameClipIds": cache["gameClipIds"], "counter": cache["counter"]})

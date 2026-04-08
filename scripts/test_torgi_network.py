import requests


URLS = [
    "https://torgi.gov.ru",
    "https://torgi.gov.ru/new/api/public/lotcards/search",
]

TIMEOUT = 15
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html",
}


def main() -> None:
    for url in URLS:
        print("---- URL ----")
        print(url)
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            print("Status: success")
            print(f"HTTP: {response.status_code}")
            body_sample = response.text[:300].replace("\n", " ").replace("\r", " ")
            print(f"Body sample: {body_sample}")
        except requests.exceptions.RequestException as exc:
            print("Status: fail")
            print(f"Exception: {type(exc).__name__}")
            print(f"Message: {exc}")
        print()


if __name__ == "__main__":
    main()

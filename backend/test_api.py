import urllib.request
import time

url = "http://localhost:5003/emails"
print(f"Fetching {url}...")
try:
    start = time.time()
    response = urllib.request.urlopen(url, timeout=10)
    data = response.read().decode('utf-8')
    print(f"Response in {time.time()-start:.2f}s: {data}")
except Exception as e:
    print(f"Error: {e}")

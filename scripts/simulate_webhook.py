#!/usr/bin/env python3
"""Send a signed local Mock Checkout webhook without persisting its raw payload."""
import argparse, hashlib, hmac, json, urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("partner_transaction_id")
parser.add_argument("--status", default="SUCCESS")
parser.add_argument("--amount", default="100.00")
parser.add_argument("--currency", default="USD")
parser.add_argument("--url", default="http://127.0.0.1:8000/api/webhooks/pingpong/checkout")
parser.add_argument("--secret", default="local-demo-secret")
args = parser.parse_args()
body = json.dumps({"partner_transaction_id": args.partner_transaction_id, "status": args.status, "amount": args.amount, "currency": args.currency}).encode()
sig = hmac.new(args.secret.encode(), body, hashlib.sha256).hexdigest()
req = urllib.request.Request(args.url, data=body, headers={"Content-Type": "application/json", "X-Mock-Signature": sig})
print(urllib.request.urlopen(req).read().decode())


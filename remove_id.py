import json

with open("processed.json", "r") as f:
    data = json.load(f)

# ID for "Istri CEO-ku Keren Sekali" is 31000896384
target_id = "31000896384"
if target_id in data:
    data.remove(target_id)
    print(f"Removed {target_id} from processed.json")
else:
    print(f"{target_id} not found in processed.json")

with open("processed.json", "w") as f:
    json.dump(data, f)

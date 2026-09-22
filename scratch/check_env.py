import os

print(f"KITE_API_KEY present: {'YES' if 'KITE_API_KEY' in os.environ else 'NO'}")
print(f"KITE_ACCESS_TOKEN present: {'YES' if 'KITE_ACCESS_TOKEN' in os.environ else 'NO'}")
print(f"DASHBOARD_API_TOKEN present: {'YES' if 'DASHBOARD_API_TOKEN' in os.environ else 'NO'}")

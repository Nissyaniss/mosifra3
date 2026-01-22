# my_diagram_script.py
from diagrams import Diagram, Cluster
from diagrams.aws.compute import EC2

# Reading a local file to decide what to draw
# This works in GitHub Actions because 'actions/checkout' pulls your files first
with open("config.txt", "r") as f:
    server_name = f.read().strip()

with Diagram("Simple Diagram", show=False):
    EC2(server_name)

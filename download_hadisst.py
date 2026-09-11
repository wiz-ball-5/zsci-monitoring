import argparse
from zsci_monitoring.download import download_hadisst

parser = argparse.ArgumentParser()
parser.add_argument("--refresh", action="store_true")
args = parser.parse_args()

download_hadisst(refresh=args.refresh)

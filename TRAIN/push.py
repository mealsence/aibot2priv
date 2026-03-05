from huggingface_hub import HfApi

api = HfApi()

# Define your repo name and the local path to your dataset
repo_id = input("repo id: ")
local_dir = input("local dir: ")

print(f"Creating repository: {repo_id}...")
# This creates the repo on the Hub (it does nothing if the repo already exists)
api.create_repo(repo_id=repo_id, repo_type="dataset", private=True, exist_ok=True)

print(f"Uploading dataset files from {local_dir}...")
# This uploads all your parquet files, MP4s, and info.json to the main branch
api.upload_folder(
    folder_path=local_dir,
    repo_id=repo_id,
    repo_type="dataset"
)

print("Setting the v3.0 tag...")
# This applies the 'v3.0' git tag to the current state of the dataset
api.create_tag(
    repo_id=repo_id,
    tag="v3.0",
    repo_type="dataset"
)

print("✅ Dataset successfully pushed and tagged as v3.0!")
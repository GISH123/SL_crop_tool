import os

def remove_gitkeep_files(root_dir='.'):
    removed_count = 0
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename == '.gitkeep':
                gitkeep_path = os.path.join(dirpath, filename)
                try:
                    os.remove(gitkeep_path)
                    removed_count += 1
                    print(f'Removed: {gitkeep_path}')
                except Exception as e:
                    print(f'Error removing {gitkeep_path}: {e}')
    print(f'\nDone. Removed {removed_count} .gitkeep file(s).')

if __name__ == "__main__":
    remove_gitkeep_files("original_dataset_structure_empty")

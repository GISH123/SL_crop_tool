import os

def add_gitkeep_to_empty_dirs(root_dir='.'):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip hidden directories like .git
        if '/.git' in dirpath or dirpath.startswith('./.git'):
            continue

        # Check if the folder is empty (no files or subdirs) or has no non-hidden files
        if not dirnames and not filenames:
            gitkeep_path = os.path.join(dirpath, '.gitkeep')
            if not os.path.exists(gitkeep_path):
                open(gitkeep_path, 'w').close()
                print(f'Added .gitkeep to empty folder: {dirpath}')
        else:
            # If it has files, check if all files are hidden (e.g., .DS_Store)
            visible_files = [f for f in filenames if not f.startswith('.')]
            if not visible_files:
                gitkeep_path = os.path.join(dirpath, '.gitkeep')
                if not os.path.exists(gitkeep_path):
                    open(gitkeep_path, 'w').close()
                    print(f'Added .gitkeep to semi-empty folder: {dirpath}')

if __name__ == "__main__":
    add_gitkeep_to_empty_dirs(root_dir="original_dataset_structure_empty")
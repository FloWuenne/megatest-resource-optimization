#!/usr/bin/env python3
"""
Generate seqerakit YAML configs and combined Nextflow configs for each pipeline.

This script:
1. Reads optimized configs from aws_megatests/optimized_configs/
2. Reads workflow metadata from aws_megatests/workflow_info/all_workflows_info.csv
3. Creates combined config files (base + optimized) in seqerakit/configs/
4. Creates YAML launch configs in seqerakit/launch_configs/
5. Generates both optimized and non-optimized variants for comparison

Note: Config files are named using Release Tags (e.g., '2.15.0') when available,
      otherwise falls back to Revision strings. Backward compatibility maintained
      for old revision-based filenames.
"""

import argparse
import csv
from pathlib import Path
import yaml


def parse_config_filename(filename):
    """
    Extract pipeline name and revision from config filename.
    Example: 'epitopeprediction_dev_optimized.config' -> ('epitopeprediction', 'dev')
    """
    # Remove '_optimized.config' suffix
    base = filename.replace('_optimized.config', '')
    # Split by underscore - last part is revision, rest is pipeline name
    parts = base.split('_')
    if len(parts) >= 2:
        revision = parts[-1]
        pipeline_name = '_'.join(parts[:-1])
        return pipeline_name, revision
    return base, None


def load_workflow_metadata(csv_path):
    """Load workflow metadata from CSV and create a lookup dictionary."""
    metadata = {}
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Extract pipeline name from repository URL
            # e.g., 'https://github.com/nf-core/epitopeprediction' -> 'epitopeprediction'
            repo = row['Repository']
            pipeline_name = repo.split('/')[-1]
            revision = row['Revision']

            # Prefer Release Tag if present, otherwise use Revision for file naming
            release_tag = row.get('Release Tag', '').strip()
            version_string = release_tag if release_tag else revision

            # Create keys for both revision and version_string to support old filenames
            key = (pipeline_name, version_string)
            metadata[key] = {
                'repository': repo,
                'revision': revision,
                'release_tag': release_tag,
                'version_string': version_string,
                'workspace_id': row['Workspace ID'],
                'commit_id': row['Commit ID'],
                'profile': row['Profile']
            }

            # Also add entry with old revision key for backward compatibility
            if revision != version_string:
                old_key = (pipeline_name, revision)
                metadata[old_key] = metadata[key].copy()
    return metadata


def create_combined_config(base_config_path, optimized_config_path, output_path):
    """Concatenate base config and optimized config."""
    with open(base_config_path, 'r') as f:
        base_config = f.read()

    with open(optimized_config_path, 'r') as f:
        optimized_config = f.read()

    combined = f"""// Combined configuration: base + optimized resources
// Base config: {base_config_path}
// Optimized config: {optimized_config_path}

{base_config}

// Optimized resource configurations
{optimized_config}
"""

    with open(output_path, 'w') as f:
        f.write(combined)


def create_yaml_config(pipeline_name, metadata, config_file, output_path, compute_env, is_optimized=True):
    """Create seqerakit YAML launch config."""
    # Construct launch name and label
    suffix = 'optimized' if is_optimized else 'baseline'
    launch_name = f'{pipeline_name}-{suffix}-test'
    label = 'test_full_optimized' if is_optimized else 'test_full'
    outdir_suffix = 'optimized' if is_optimized else 'baseline'

    # Use test_full profile (extract first profile if multiple)
    profile = 'test_full'
    if ',' in metadata['profile']:
        profiles = [p.strip() for p in metadata['profile'].split(',')]
        # Keep test_full and exclude docker/aws_tower specific profiles
        profile = ','.join([p for p in profiles if p in ['test_full']])

    launch_config = {
        'name': launch_name,
        'workspace': 'nf-core/ResourceOptimization',
        'pipeline': metadata['repository'],
        'compute-env': compute_env,
        'profile': profile,
        'revision': metadata['revision'],
        'config': config_file,
        'labels': label,
        'params': {
            'outdir': f"s3://nf-core-resource-optimization/{pipeline_name}/test_full/{outdir_suffix}"
        },
        'work-dir': 's3://nf-core-resource-optimization'
    }

    config = {'launch': [launch_config]}

    with open(output_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Generate seqerakit YAML configs and combined Nextflow configs for each pipeline.'
    )
    parser.add_argument(
        '--compute-env',
        default='aws_ireland_fusionv2_nvme_cpu_snapshots',
        help='Compute environment name to use for launches (default: aws_ireland_fusionv2_nvme_cpu_snapshots)'
    )
    args = parser.parse_args()

    # Setup paths
    base_dir = Path(__file__).parent
    optimized_configs_dir = base_dir / 'aws_megatests' / 'optimized_configs'
    workflow_csv = base_dir / 'aws_megatests' / 'workflow_info' / 'all_workflows_info.csv'
    base_config = base_dir / 'seqerakit' / 'nextflow.config'

    # Output directories
    combined_configs_dir = base_dir / 'seqerakit' / 'configs'
    yaml_configs_dir = base_dir / 'seqerakit' / 'launch_configs'

    # Create output directories
    combined_configs_dir.mkdir(parents=True, exist_ok=True)
    yaml_configs_dir.mkdir(parents=True, exist_ok=True)

    # Load workflow metadata
    print(f"Loading workflow metadata from {workflow_csv}")
    print(f"Using compute environment: {args.compute_env}")
    metadata = load_workflow_metadata(workflow_csv)
    print(f"Loaded metadata for {len(metadata)} workflows")

    # Process each optimized config
    config_files = sorted(optimized_configs_dir.glob('*_optimized.config'))
    print(f"\nFound {len(config_files)} optimized config files")

    generated_optimized = 0
    generated_baseline = 0
    skipped_count = 0

    for config_file in config_files:
        pipeline_name, revision = parse_config_filename(config_file.name)
        key = (pipeline_name, revision)

        if key not in metadata:
            print(f"⚠️  Skipping {config_file.name}: No metadata found for {pipeline_name} {revision}")
            skipped_count += 1
            continue

        pipeline_metadata = metadata[key]
        version_str = pipeline_metadata['version_string']

        # 1. Create OPTIMIZED config (base + optimized resources)
        optimized_config_path = combined_configs_dir / f'{pipeline_name}_{version_str}_optimized.config'
        create_combined_config(base_config, config_file, optimized_config_path)

        # Create YAML config for optimized run
        relative_optimized_config = f'./configs/{pipeline_name}_{version_str}_optimized.config'
        yaml_optimized_path = yaml_configs_dir / f'{pipeline_name}_{version_str}_optimized.yml'
        create_yaml_config(pipeline_name, pipeline_metadata, relative_optimized_config,
                          yaml_optimized_path, args.compute_env, is_optimized=True)
        generated_optimized += 1

        # 2. Create BASELINE config (base only, no optimized resources)
        baseline_config_path = combined_configs_dir / f'{pipeline_name}_{version_str}_baseline.config'
        with open(base_config, 'r') as f:
            base_content = f.read()

        baseline_content = f"""// Baseline configuration (base only, no resource optimization)
// Base config: {base_config}

{base_content}
"""
        with open(baseline_config_path, 'w') as f:
            f.write(baseline_content)

        # Create YAML config for baseline run
        relative_baseline_config = f'./configs/{pipeline_name}_{version_str}_baseline.config'
        yaml_baseline_path = yaml_configs_dir / f'{pipeline_name}_{version_str}_baseline.yml'
        create_yaml_config(pipeline_name, pipeline_metadata, relative_baseline_config,
                          yaml_baseline_path, args.compute_env, is_optimized=False)
        generated_baseline += 1

        print(f"✓ Generated configs for {pipeline_name} ({version_str}): optimized + baseline")

    print(f"\n{'='*60}")
    print("Summary:")
    print(f"  Generated optimized configs: {generated_optimized}")
    print(f"  Generated baseline configs: {generated_baseline}")
    print(f"  Skipped: {skipped_count} (no metadata)")
    print(f"\nOutput locations:")
    print(f"  Combined configs: {combined_configs_dir}")
    print(f"  YAML configs: {yaml_configs_dir}")
    print(f"\nLabels for filtering:")
    print("  Optimized runs: 'test_full_optimized'")
    print("  Baseline runs: 'test_full'")
    print("="*60)


if __name__ == '__main__':
    main()

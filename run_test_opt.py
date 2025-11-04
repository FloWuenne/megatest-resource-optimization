import json
import os

with open('pipelines.json', 'r') as f:
    pipelines_json = json.load(f)

released = []
for pipeline in pipelines_json['remote_workflows']:
    for release in pipeline['releases']:
        if release['tag_name'] != 'dev':
            released.append(pipeline)
            break

with open('tw_cli_opt.yml', 'w') as cli:
    cli.write('launch:\n')

re_run = ['drugresponseeval','denovotranscript','airrflow','hic','hicar','isoseq','metaboigniter','metatdenovo','methylong','methylseq','mhcquant','molkart','multiplesequencealign','nanoseq','nanostring','nascent','pacvar','pangenome','phaseimpute','phyloplace','pixelator','proteinfamilies','rangeland','raredisease','reportho','riboseq','rnasplice','rnavar','sarek','scnanoseq','scrnaseq','smrnaseq','taxprofiler','variantbenchmarking','viralintegration','viralrecon','oncoanalyser']

config_files = os.listdir('optimized_configs_tests')
for conf_file in config_files:
    out_plugin_conf = 'optimized_configs_tests/' + conf_file.split('.')[0] + '-CO2plugin.config'
    name = conf_file.split('-')[0]
    if name in re_run:
        pipeline = next((p for p in released if p.get("name") == name), None)
        os.system(f'cat optimized_configs_tests/{conf_file} nextflow.config > {out_plugin_conf}')
        with open('tw_cli_opt.yml', 'a') as cli:
            if not pipeline['archived']:
                pipeline['repository_url']
                cli.write(f'  - name: "{pipeline['name']}-test"\n')
                cli.write(f'    workspace: "nf-core/ResourceOptimization"\n')
                cli.write(f'    compute-env: "aws_ireland_fusionv2_nvme_cpu_snapshots"\n')
                cli.write(f'    pipeline: "{pipeline['repository_url']}"\n')
                cli.write(f'    revision: "{pipeline['releases'][0]['tag_name']}"\n')
                cli.write(f'    labels: "testPostOpt"\n')
                cli.write(f'    profile: "test"\n')
                cli.write(f'    config: "{out_plugin_conf}"\n')
                # cli.write(f'    work-dir: "s3://nf-core-resource-optimization"\n')
                cli.write(f'    work-dir: "s3://nf-core-awsmegatests/resource_optimizations/work"\n')
                cli.write(f'    params:\n')
                # cli.write(f'      outdir: "s3://nf-core-resource-optimization/{pipeline['name']}/test/not_optimized"\n')
                # cli.write(f'      outdir: "s3://nf-core-awsmegatests/resource_optimizations/{pipeline['name']}/test/not_optimized"\n')
                cli.write(f'      outdir: "results/"\n')

os.system('seqerakit tw_cli_opt.yml')
os.system('rm optimized_configs_tests/*CO2plugin*')
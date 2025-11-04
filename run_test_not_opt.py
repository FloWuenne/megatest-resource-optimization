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

# failed = ['fastquorum', 'eager', 'dualrnaseq', 'drugresponseeval', 'diaproteomics', 'denovotranscript', 'deepvariant', 'createtaxdb', 'coproid', 'clipseq', 'circdna', 'cageseq', 'bactmap', 'ampliseq', 'airrflow', 'rnaseq']
# succeded = ['genomeassembler', 'funcscan', 'fetchngs', 'fastqrepair', 'epitopeprediction', 'differentialabundance', 'detaxizer', 'demultiplex', 'demo', 'cutandrun', 'crisprseq', 'chipseq', 'callingcards', 'bamtofastq', 'bacass', 'atacseq', 'rnaseq']
# submitted = ['kmermaid', 'isoseq', 'imcyto', 'hlatyping', 'hicar', 'hic']
# not_submitted = ['hgtseq', 'longraredisease']
re_run = ['drugresponseeval','denovotranscript','airrflow','hic','hicar','isoseq','metaboigniter','metatdenovo','methylong','methylseq','mhcquant','molkart','multiplesequencealign','nanoseq','nanostring','nascent','pacvar','pangenome','phaseimpute','phyloplace','pixelator','proteinfamilies','rangeland','raredisease','reportho','riboseq','rnasplice','rnavar','sarek','scnanoseq','scrnaseq','smrnaseq','taxprofiler','variantbenchmarking','viralintegration','viralrecon','oncoanalyser']


with open('tw_cli_not_opt.yml', 'w') as cli:
    cli.write('launch:\n')
    for pipeline in released:
        if not pipeline['archived']:
            if pipeline['name'] in re_run:
                pipeline['repository_url']
                cli.write(f'  - name: "{pipeline['name']}-test"\n')
                cli.write(f'    workspace: "nf-core/ResourceOptimization"\n')
                cli.write(f'    compute-env: "aws_ireland_fusionv2_nvme_cpu_snapshots"\n')
                cli.write(f'    pipeline: "{pipeline['repository_url']}"\n')
                cli.write(f'    revision: "{pipeline['releases'][0]['tag_name']}"\n')
                cli.write(f'    labels: "testPreOpt"\n')
                cli.write(f'    profile: "test"\n')
                cli.write(f'    config: "./nextflow.config"\n')
                # cli.write(f'    work-dir: "s3://nf-core-resource-optimization"\n')
                cli.write(f'    work-dir: "s3://nf-core-awsmegatests/resource_optimizations/work"\n')
                cli.write(f'    params:\n')
                # cli.write(f'      outdir: "s3://nf-core-resource-optimization/{pipeline['name']}/test/not_optimized"\n')
                # cli.write(f'      outdir: "s3://nf-core-awsmegatests/resource_optimizations/{pipeline['name']}/test/not_optimized"\n')
                cli.write(f'      outdir: "results/"\n')

os.system('seqerakit tw_cli_not_opt.yml')

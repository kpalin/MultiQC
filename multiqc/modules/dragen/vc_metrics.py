#!/usr/bin/env python
from __future__ import print_function
from collections import OrderedDict, defaultdict
from multiqc.modules.base_module import BaseMultiqcModule
from multiqc.plots import linegraph, table

# Initialise the logger
import logging

log = logging.getLogger(__name__)


class DragenVCMetrics(BaseMultiqcModule):
    def parse_vc_metrics(self):
        all_data_by_sample = dict()

        for f in self.find_log_files('dragen/vc_metrics'):
            data_by_sample = parse_vc_metrics_file(f)
            if data_by_sample:
                for sn, data in data_by_sample.items():
                    if sn in all_data_by_sample:
                        log.debug('Duplicate sample name found! Overwriting: {}'.format(f['s_name']))
                    self.add_data_source(f, section='stats')

                    all_data_by_sample[sn] = data

        # Filter to strip out ignored sample names:
        all_data_by_sample = self.ignore_samples(all_data_by_sample)

        if not all_data_by_sample:
            return
        log.info('Found variant calling metrics for {} samples'.format(len(all_data_by_sample)))

        all_metric_names = set()
        for sn, sdata in all_data_by_sample.items():
            for m in sdata.keys():
                all_metric_names.add(m)

        gen_stats_headers, vc_table_headers = make_headers(all_metric_names)

        self.general_stats_addcols(all_data_by_sample, gen_stats_headers, 'Variant calling')

        self.add_section(
            name='Variant calling',
            anchor='dragen-vc-metrics',
            description='Variant calling metrics. Metrics are reported for each sample in multi sample VCF '
                        'and gVCF files. Based on the run case, metrics are reported either as standard '
                        'VARIANT CALLER or JOINT CALLER. All metrics are reported for post-filter VCFs, '
                        'except for the "Filtered" metrics which represent how many variants were filtered out'
                        'from pre-filter VCF to generate the post-filter VCF.',
            plot=table.plot(all_data_by_sample, vc_table_headers)
        )


vc_metrics = [
    # id_in_data                                              title (display name)   gen_stats  vc_table  description
    # Read stats:
    ('Total'                                                  , 'Vars'                , '#',  '#',  'Total number of variants (SNPs + MNPs + INDELS).'),
    ('Reads Processed'                                        , 'VC reads'            , None, None, 'The number of reads used for variant calling, excluding any duplicate marked reads and reads falling outside of the target region'),
    ('Biallelic'                                              , 'Biallelic'           , None, None, 'Number of sites in a genome that contains two observed alleles, counting the reference as one, and therefore allowing for one variant allele'),
    ('Multiallelic'                                           , 'Multiallelic'        , None, '%',  'Number of sites in the VCF that contain three or more observed alleles. The reference is counted as one, therefore allowing for two or more variant alleles'),
    ('SNPs'                                                   , 'SNPs'                , None, '%',  'Number of SNPs in the variant set. A variant is counted as an SNP when the reference, allele 1, and allele2 are all length 1'),
    ('Indels'                                                 , 'Indels'              , None, '%',  'Number of insetions and deletions in the variant set.'),
    ('Insertions'                                             , 'Ins'                 , None, None, ''),
    ('Deletions'                                              , 'Del'                 , None, None, ''),
    ('Insertions (Hom)'                                       , 'Hom ins'             , None, None, 'Number of variants that contains homozygous insertions'),
    ('Insertions (Het)'                                       , 'Het ins'             , None, None, 'Number of variants where both alleles are insertions, but not homozygous'),
    ('Deletions (Hom)'                                        , 'Hom del'             , None, None, 'Number of variants that contains homozygous deletions'),
    ('Deletions (Het)'                                        , 'Het del'             , None, None, 'Number of variants where both alleles are deletion, but not homozygous'),
    ('Indels (Het)'                                           , 'Het indel'           , None, None, 'Number of variants where genotypes are either [insertion+deletion], [insertion+snp] or [deletion+snp].'),
    ('DeNovo SNPs'                                            , 'DeNovo SNPs'         , None, None, 'Number of DeNovo marked SNPs, with DQ > 0.05. Set the --qc-snp-denovo-quality-threshold option to the required threshold. The default is 0.05.'),
    ('DeNovo INDELs'                                          , 'DeNovo indel'        , None, None, 'Number of DeNovo marked indels, with DQ > 0.05. Set the --qc-snp-denovo-quality-threshold option to the required threshold. The default is 0.05.'),
    ('DeNovo MNPs'                                            , 'DeNovo MNPs'         , None, None, 'Number of DeNovo marked MNPs, with DQ > 0.05. Set the --qc-snp-denovo-quality-threshold option to the required threshold. The default is 0.05.'),
    ('Chr X number of SNPs over genome'                       , 'ChrX SNP'            , None, None, 'Number of SNPs in chromosome X (or in the intersection of chromosome X with the target region). '
                                                                                                    'If there was no alignment to either chromosome X, this metric shows as NA'),
    ('Chr Y number of SNPs over genome'                       , 'ChrY SNP'            , None, None, 'Number of SNPs in chromosome Y (or in the intersection of chromosome Y with the target region). '
                                                                                                    'If there was no alignment to either chromosome Y, this metric shows as NA'),
    ('(Chr X SNPs)/(chr Y SNPs) ratio over genome'            , 'X/Y SNP ratio'       , None, None, 'Number of SNPs in chromosome X (or in the intersection of chromosome X with the target region) '
                                                                                                    'divided by the number of SNPs in chromosome Y (or in the intersection of chromosome Y with the '
                                                                                                    'target region). If there was no alignment to either chromosome X or chromosome Y, this metric '
                                                                                                    'shows as NA'),
    ('SNP Transitions'                                        , 'SNP Ti'              , None, None, 'Number of transitions - interchanges of two purines (A<->G) or two pyrimidines (C<->T)'),
    ('SNP Transversions'                                      , 'SNP Tv'              , None, None, 'Number of transversions - interchanges of purine and pyrimidine bases'),
    ('Ti/Tv ratio'                                            , 'Ti/Tv'               , None, '#' , 'Ti/Tv ratio: ratio of transitions to transitions.'),
    ('Heterozygous'                                           , 'Het'                 , None, None, 'Number of heterozygous variants'),
    ('Homozygous'                                             , 'Hom'                 , None, None, 'Number of homozygous variants'),
    ('Het/Hom ratio'                                          , 'Het/Hom'             , None, '%' , 'Heterozygous/ homozygous ratio'),
    ('In dbSNP'                                               , 'In dbSNP'            , None, '%' , 'Number of variants detected that are present in the dbsnp reference file. If no dbsnp file '
                                                                                                    'is provided via the --bsnp option, then both the In dbSNP and Novel metrics show as NA.'),
    ('Not in dbSNP'                                           , 'Novel'               , None, None, 'Number of all variants minus number of variants in dbSNP. If no dbsnp file '
                                                                                                    'is provided via the --bsnp option, then both the In dbSNP and Novel metrics show as NA.'),
    ('Percent Callability'                                    , 'Callability'         , None, '#' , 'Available only in germline mode with gVCF output. The percentage of non-N reference '
                                                                                                    'positions having a PASSing genotype call. Multi-allelic variants are not counted. '
                                                                                                    'Deletions are counted for all the deleted reference positions only for homozygous calls. '
                                                                                                    'Only autosomes and chromosomes X, Y and M are considered.'),
    ('Percent Autosome Callability'                           , 'Autosome callability', None, None, 'Available only in germline mode with gVCF output. The percentage of non-N reference '
                                                                                                    'positions having a PASSing genotype call. Multi-allelic variants are not counted. '
                                                                                                    'Deletions are counted for all the deleted reference positions only for homozygous calls. '
                                                                                                    'Only autosomes are considered (for all chromosomes, see the Callability metric).'),
    ('Filtered vars'                                          , 'Filtered'            , None, '%' , 'Number of raw variants minus the number of PASSed variants'),
    ('Filtered SNPs'                                          , 'Filt SNPs'           , None, None, 'Number of raw SNPs minus the number of PASSed SNPs'),
    ('Filtered indels'                                        , 'Filt indels'         , None, None, 'Number of raw indels minus the number of PASSed indels'),
]

def make_headers(metric_names):
    # Init general stats table
    gen_stats_headers = OrderedDict()

    # Init the VC table
    vc_table_headers = OrderedDict()

    for id_in_data, title, in_gen_stats, in_vc_table, descr in vc_metrics:
        col = dict(
            title=title,
            description=descr,
            min=0,
        )
        gen_stats_headers[id_in_data] = dict(col, hidden=in_gen_stats != '#')
        vc_table_headers[id_in_data] = dict(col, hidden=in_vc_table != '#')

        if id_in_data + ' pct' in metric_names:
            # if % value is available, showing it instead of the number value; the number value will be hidden
            pct_col = dict(
                col,
                description=descr.replace(', {}', '').replace('Number of ', '% of '),
                max=100,
                suffix='%',
            )
            gen_stats_headers[id_in_data + ' pct'] = dict(pct_col, hidden=in_gen_stats != '%')
            vc_table_headers[id_in_data + ' pct'] = dict(pct_col, hidden=in_vc_table != '%')

    return gen_stats_headers, vc_table_headers


def parse_vc_metrics_file(f):
    """
    T_SRR7890936_50pc.vc_metrics.csv

    VARIANT CALLER SUMMARY,,Number of samples,1
    VARIANT CALLER SUMMARY,,Reads Processed,2721782043
    VARIANT CALLER SUMMARY,,Child Sample,NA
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Total,170013,100.00
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Biallelic,170013,100.00
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Multiallelic,0,0.00
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,SNPs,138978,81.75
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Insertions (Hom),0,0.00
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Insertions (Het),14291,8.41
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Deletions (Hom),0,0.00
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Deletions (Het),16744,9.85
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Indels (Het),0,0.00
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Chr X number of SNPs over genome,32487
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Chr Y number of SNPs over genome,131
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,(Chr X SNPs)/(chr Y SNPs) ratio over genome,247.99
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,SNP Transitions,79948
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,SNP Transversions,59025
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Ti/Tv ratio,1.35
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Heterozygous,170013
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Homozygous,0
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Het/Hom ratio,0.00
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,In dbSNP,0,0.00
    VARIANT CALLER PREFILTER,T_SRR7890936_50pc,Not in dbSNP,0,0.00
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Total,123219,100.00
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Biallelic,123219,100.00
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Multiallelic,0,0.00
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,SNPs,104900,85.13
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Insertions (Hom),0,0.00
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Insertions (Het),8060,6.54
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Deletions (Hom),0,0.00
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Deletions (Het),10259,8.33
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Indels (Het),0,0.00
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Chr X number of SNPs over genome,28162
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Chr Y number of SNPs over genome,8
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,(Chr X SNPs)/(chr Y SNPs) ratio over genome,3520.25
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,SNP Transitions,62111
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,SNP Transversions,42789
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Ti/Tv ratio,1.45
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Heterozygous,123219
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Homozygous,0
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Het/Hom ratio,0.00
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,In dbSNP,0,0.00
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Not in dbSNP,0,0.00
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Percent Callability,NA
    VARIANT CALLER POSTFILTER,T_SRR7890936_50pc,Percent Autosome Callability,NA
    """
    sample = f['fn'].split('.vc_metrics.csv')[0]

    prefilter_data_by_sample = defaultdict(dict)
    postfilter_data_by_sample = defaultdict(dict)

    for line in f['f'].splitlines():
        fields = line.split(',')
        analysis = fields[0]
        # sample = fields[1]
        metric = fields[2]
        value = fields[3]

        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass

        percentage = None
        if len(fields) > 4:  # percentage
            percentage = fields[4]
            try:
                percentage = float(percentage)
            except ValueError:
                pass

        if analysis == 'VARIANT CALLER SUMMARY':
            prefilter_data_by_sample[sample][metric] = value

        if analysis == 'VARIANT CALLER PREFILTER':
            prefilter_data_by_sample[sample][metric] = value

        if analysis == 'VARIANT CALLER POSTFILTER':
            postfilter_data_by_sample[sample][metric] = value
            if percentage is not None:
                postfilter_data_by_sample[sample][metric + ' pct'] = percentage

    # adding few more metrics: total insertions, deletions and indels numbers
    for d in [prefilter_data_by_sample, postfilter_data_by_sample]:
        for sname, data in d.items():
            data['Insertions'] = data['Insertions (Hom)'] + data['Insertions (Het)']
            data['Deletions']  = data['Deletions (Hom)']  + data['Deletions (Het)']
            data['Indels']     = data['Insertions']       + data['Deletions']
            if data['Total'] != 0:
                data['Insertions pct'] = data['Insertions'] / data['Total']
                data['Deletions pct']  = data['Deletions']  / data['Total']
                data['Indels pct']     = data['Indels']     / data['Total']

    data_by_sample = postfilter_data_by_sample
    # we are not really interested in all the details of pre-filtered variants, however
    # it would be nice to report how much we filtered out
    for sname, data in data_by_sample.items():
        data['Filtered vars']     = prefilter_data_by_sample[sname]['Total']  - data['Total']
        data['Filtered SNPs']     = prefilter_data_by_sample[sname]['SNPs']   - data['SNPs']
        data['Filtered indels']   = prefilter_data_by_sample[sname]['Indels'] - data['Indels']
        if prefilter_data_by_sample['Total'] != 0:
            data['Filtered vars pct']   = data['Filtered vars']     / prefilter_data_by_sample[sname]['Total']
        if prefilter_data_by_sample['SNPs'] != 0:
            data['Filtered SNPs pct']   = data['Filtered SNPs']     / prefilter_data_by_sample[sname]['SNPs']
        if prefilter_data_by_sample['Indels'] != 0:
            data['Filtered indels pct'] = data['Filtered indels']   / prefilter_data_by_sample[sname]['Indels']

    return data_by_sample














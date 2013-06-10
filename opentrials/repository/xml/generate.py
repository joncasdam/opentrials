import datetime

from django.template.loader import render_to_string
from django.conf import settings

from repository import choices
from repository.xml import OPENTRIALS_XML_VERSION
from repository.templatetags.repository_tags import prep_label_for_xml

from vocabulary.models import CountryCode, InterventionCode, StudyPurpose
from vocabulary.models import InterventionAssigment, StudyMasking, StudyAllocation
from vocabulary.models import StudyPhase, StudyType, RecruitmentStatus, InstitutionType

VALID_FUNCTIONS = (
    'xml_ictrp',
    'xml_opentrials',
    'xml_opentrials_mod',
    )

def formatted_institution_address(institution):
    """Return a formatted string like: ICICT - Rio de Janeiro, RJ, Brasil"""
    return institution['name']+' - '+', '.join(
        i for i in [institution.get('city'),institution.get('state'),
                    institution['country']['description']
                    ] if i
        )

def xml_ictrp(fossils, **kwargs):
    """Generates an ICTRP XML for a given Clinical Trial and returns as string."""

    trials = []

    for fossil in fossils:
        trial = {}
        ct_fossil = fossil.get_object_fossil()
        trial['ct_fossil'] = ct_fossil
        trial['public_contact'] = ct_fossil.public_contact if ct_fossil.public_contact \
                                            else ct_fossil.scientific_contact
        trial['primary_sponsor'] = formatted_institution_address(ct_fossil.primary_sponsor)
        trial['secondary_sponsors'] = [formatted_institution_address(sponsor['institution'])
                                        for sponsor in ct_fossil.secondary_sponsors]
        trial['source_support'] = [formatted_institution_address(source['institution'])
                                        for source in ct_fossil.support_sources]
        trial['hash_code'] = fossil.pk
        trial['previous_revision'] = fossil.previous_revision
        trial['version'] = fossil.revision_sequential
        trials.append(trial)

    return render_to_string(
            'repository/xml/all_xml_ictrp.xml', # old clinicaltrial_detail.xml
            {'trial_list': trials, 'reg_name': settings.REG_NAME},
            )

INCLUSION_GENDER = [('-','Ambos'), ('M', 'Masculino'), ('F', 'Feminino'),]
    
INCLUSION_AGE_UNIT = [
    ('-', 'Sem limite'),
    ('Y', 'anos'),
    ('M', 'meses'),
    ('W', 'semanas'),
    ('D', 'dias'),
    ('H', 'horas'),
]

BOLEANO = [(True, 'Sim'), (False, 'Nao'), (None, 'Desconhecido')]

def TrialDicList(trials):
    trial_dic_list = []

    for ct in trials:
        translations = [t for t in ct.translations.all()]

        def campo(field,language):
            retorno = [eval("trans.%s" % field) for trans in translations if trans.language == language][0]
            return retorno

        except_msg = 'Nao definido - id: %s' % ct.id

        trial_dic = {}

        try:
            observational = ct.is_observational
            if observational:
                trial_dic['TIPO_DE_ESTUDO'] = 'observacional'
            else:
                trial_dic['TIPO_DE_ESTUDO'] = 'intervencao'
        except:
            trial_dic['TIPO_DE_ESTUDO'] = except_msg

        try:
            trial_dic['TITULO_CIENTIFICO_PT'] = campo('scientific_title', 'pt-br')
        except:
            trial_dic['TITULO_CIENTIFICO_PT'] = except_msg

        try:
            trial_dic['TITULO_CIENTIFICO_ES'] = campo('scientific_title', 'es')
        except:
            trial_dic['TITULO_CIENTIFICO_ES'] = except_msg

        try:
            trial_dic['TITULO_CIENTIFICO_EN'] = ct.scientific_title
        except:
            trial_dic['TITULO_CIENTIFICO_EN'] = except_msg

        try:
            trial_dic['UTN'] = ct.utrn_number
        except:
            trial_dic['UTN'] = except_msg

        try:
            trial_dic['TITULO_PUBLICO_PT'] = campo('public_title', 'pt-br')
        except:
            trial_dic['TITULO_PUBLICO_PT'] = except_msg

        try:
            trial_dic['TITULO_PUBLICO_ES'] = campo('public_title', 'es')
        except:
            trial_dic['TITULO_PUBLICO_ES'] = except_msg

        try:
            trial_dic['TITULO_PUBLICO_EN'] = ct.public_title
        except:
            trial_dic['TITULO_PUBLICO_EN'] = except_msg

        try:
            trial_dic['ACRONIMO_CIENTIFICO_PT'] = campo('scientific_acronym', 'pt-br')
        except:
            trial_dic['ACRONIMO_CIENTIFICO_PT'] = except_msg

        try:
            trial_dic['ACRONIMO_CIENTIFICO_ES'] = campo('scientific_acronym', 'es')
        except:
            trial_dic['ACRONIMO_CIENTIFICO_ES'] = except_msg

        try:
            trial_dic['ACRONIMO_CIENTIFICO_EN'] = ct.scientific_acronym
        except:
            trial_dic['ACRONIMO_CIENTIFICO_EN'] = except_msg

        secondary_ids_list = []            
        sec_id_index = 1
        for secid in ct.trial_number():
            secondary_ids_list.append(secid)
            if sec_id_index == 3:
                break
            sec_id_index += 1
        
        try:
            trial_dic['ID_SECUNDARIOS_1'] = secondary_ids_list[0]
        except:
            trial_dic['ID_SECUNDARIOS_1'] = except_msg

        try:
            trial_dic['ID_SECUNDARIOS_2'] = secondary_ids_list[1]
        except:
            trial_dic['ID_SECUNDARIOS_2'] = except_msg

        try:
            trial_dic['ID_SECUNDARIOS_3'] = secondary_ids_list[2]
        except:
            trial_dic['ID_SECUNDARIOS_3'] = except_msg

        try:
            trial_dic['PATROCINADOR_PRIMARIO'] = ct.primary_sponsor.name
        except:
            trial_dic['PATROCINADOR_PRIMARIO'] = except_msg

        secondary_sponsor_list = [] 
        sec_sponsor_index = 1
        for sponsor in ct.secondary_sponsors():
            secondary_sponsor_list.append(sponsor)
            if sec_sponsor_index == 2:
                break
            sec_sponsor_index = sec_sponsor_index + 1

        try:
            trial_dic['PATROCINADOR_SECUNDARIO_1'] = secondary_sponsor_list[0]
        except:
            trial_dic['PATROCINADOR_SECUNDARIO_1'] = except_msg

        try:
            trial_dic['PATROCINADOR_SECUNDARIO_2'] = secondary_sponsor_list[1]
        except:
            trial_dic['PATROCINADOR_SECUNDARIO_2'] = except_msg

        source_support_list = []
        source_support_index = 1
        for source in ct.support_sources():
            source_support_list.append(source)
            if source_support_index == 2:
                break
            source_support_index = source_support_index + 1

        try:
            trial_dic['APOIO_FINANCEIRO_OU_MATERIAL_1'] = source_support_list[0]
        except:
            trial_dic['APOIO_FINANCEIRO_OU_MATERIAL_1'] = except_msg

        try:
            trial_dic['APOIO_FINANCEIRO_OU_MATERIAL_2'] = source_support_list[1]
        except:
            trial_dic['APOIO_FINANCEIRO_OU_MATERIAL_2'] = except_msg


        try:
            trial_dic['CONDICOES_DE_SAUDE_PT'] = campo('hc_freetext', 'pt-br')
        except:
            trial_dic['CONDICOES_DE_SAUDE_PT'] = except_msg

        try:
            trial_dic['CONDICOES_DE_SAUDE_ES'] = campo('hc_freetext', 'es')
        except:
            trial_dic['CONDICOES_DE_SAUDE_ES'] = except_msg

        try:
            trial_dic['CONDICOES_DE_SAUDE_EN'] = ct.hc_freetext
        except:
            trial_dic['CONDICOES_DE_SAUDE_EN'] = except_msg

        health_condition_code_list = []
        hc_code_index = 1
        hc_list = []
        for hc in ct.hc_code():
            for t in hc.translations_all():
                if t.language == 'es':
                    texto_es = t.text
                if t.language == 'pt-br':
                    texto_pt = t.text

            hc_list = [hc.code, hc.text, texto_pt, texto_es, hc.vocabulary]

            health_condition_code_list.append(hc_list)
            if hc_code_index == 2:
                break
            hc_code_index += 1

        try:
            trial_dic['DESCRITORES_GERAIS_1_PT'] = '[%s] %s: %s' % (health_condition_code_list[0][4], health_condition_code_list[0][0], health_condition_code_list[0][2])
        except:
            trial_dic['DESCRITORES_GERAIS_1_PT'] = except_msg

        try:
            trial_dic['DESCRITORES_GERAIS_2_PT'] = '[%s] %s: %s' % (health_condition_code_list[1][4], health_condition_code_list[1][0], health_condition_code_list[1][2])
        except:
            trial_dic['DESCRITORES_GERAIS_2_PT'] = except_msg

        try:
            trial_dic['DESCRITORES_GERAIS_1_EN'] = '[%s] %s: %s' % (health_condition_code_list[0][4], health_condition_code_list[0][0], health_condition_code_list[0][1])
        except:
            trial_dic['DESCRITORES_GERAIS_1_EN'] = except_msg

        try:
            trial_dic['DESCRITORES_GERAIS_2_EN'] = '[%s] %s: %s' % (health_condition_code_list[1][4], health_condition_code_list[0][0], health_condition_code_list[1][1])
        except:
            trial_dic['DESCRITORES_GERAIS_2_EN'] = except_msg

        try:
            trial_dic['DESCRITORES_GERAIS_1_ES'] = '[%s] %s: %s' % (health_condition_code_list[0][4], health_condition_code_list[0][0], health_condition_code_list[0][3])
        except:
            trial_dic['DESCRITORES_GERAIS_1_ES'] = except_msg

        try:
            trial_dic['DESCRITORES_GERAIS_2_ES'] = '[%s] %s: %s' % (health_condition_code_list[1][4], health_condition_code_list[1][0], health_condition_code_list[1][3])
        except:
            trial_dic['DESCRITORES_GERAIS_2_ES'] = except_msg

        health_condition_keyword_list = []
        hc_key_index = 1
        hc_list = []
        for hc in ct.hc_keyword():
            for t in hc.translations_all():
                if t.language == 'es':
                    texto_es = t.text
                if t.language == 'pt-br':
                    texto_pt = t.text

            hc_list = [hc.code, hc.text, texto_pt, texto_es, hc.vocabulary]

            health_condition_keyword_list.append(hc_list)
            if hc_key_index == 2:
                break
            hc_key_index =+ 1

        try:
            trial_dic['DESCRITORES_ESPECIFICOS_1_PT'] = '[%s] %s: %s' % (health_condition_keyword_list[0][4], health_condition_keyword_list[0][0], health_condition_keyword_list[0][2])
        except:
            trial_dic['DESCRITORES_ESPECIFICOS_1_PT'] = except_msg

        try:
            trial_dic['DESCRITORES_ESPECIFICOS_2_PT'] = '[%s] %s: %s' % (health_condition_keyword_list[1][4], health_condition_keyword_list[1][0], health_condition_keyword_list[1][2])
        except:
            trial_dic['DESCRITORES_ESPECIFICOS_2_PT'] = except_msg

        try:
            trial_dic['DESCRITORES_ESPECIFICOS_1_EN'] = '[%s] %s: %s' % (health_condition_keyword_list[0][4], health_condition_keyword_list[0][0], health_condition_keyword_list[0][1])
        except:
            trial_dic['DESCRITORES_ESPECIFICOS_1_EN'] = except_msg

        try:
            trial_dic['DESCRITORES_ESPECIFICOS_2_EN'] = '[%s] %s: %s' % (health_condition_keyword_list[1][4], health_condition_keyword_list[1][0], health_condition_keyword_list[1][1])
        except:
            trial_dic['DESCRITORES_ESPECIFICOS_2_EN'] = except_msg

        try:
            trial_dic['DESCRITORES_ESPECIFICOS_1_ES'] = '[%s] %s: %s' % (health_condition_keyword_list[0][4], health_condition_keyword_list[0][0], health_condition_keyword_list[0][3])
        except:
            trial_dic['DESCRITORES_ESPECIFICOS_1_ES'] = except_msg

        try:
            trial_dic['DESCRITORES_ESPECIFICOS_2_ES'] = '[%s] %s: %s' % (health_condition_keyword_list[1][4], health_condition_keyword_list[1][0], health_condition_keyword_list[1][3])
        except:
            trial_dic['DESCRITORES_ESPECIFICOS_2_ES'] = except_msg

        intervention_code_list = []
        i_code_index = 1
        i_list = []
        for iv in ct.intervention_code():
            for t in iv.translations.all():
                if t.language == 'pt-br':
                    texto_pt = t.label
                if t.language == 'es':
                    texto_es = t.label

            i_list = [iv.label, texto_pt, texto_es]

            intervention_code_list.append(i_list)
            if i_code_index == 2:
                break
            i_code_index += 1

        try:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_1_PT'] = intervention_code_list[0][1]
        except:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_1_PT'] = except_msg

        try:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_2_PT'] = intervention_code_list[1][1]
        except:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_2_PT'] = except_msg

        try:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_1_EN'] = intervention_code_list[0][0]
        except:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_1_EN'] = except_msg

        try:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_2_EN'] = intervention_code_list[1][0]
        except:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_2_EN'] = except_msg

        try:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_1_ES'] = intervention_code_list[0][2]
        except:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_1_ES'] = except_msg

        try:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_2_ES'] = intervention_code_list[1][2]
        except:
            trial_dic['CATEGORIA_DAS_INTERVENCOES_2_ES'] = except_msg

        try:
            trial_dic['INTERVENCOES_PT'] = campo('i_freetext', 'pt-br')
        except:
            trial_dic['INTERVENCOES_PT'] = except_msg

        try:
            trial_dic['INTERVENCOES_ES'] = campo('i_freetext', 'es')
        except:
            trial_dic['INTERVENCOES_ES'] = except_msg

        try:
            trial_dic['INTERVENCOES_EN'] = ct.i_freetext
        except:
            trial_dic['INTERVENCOES_EN'] = except_msg

        intervention_keyword_list = []
        i_key_index = 1
        hc_list = []
        for hc in ct.hc_code():
            for t in hc.translations.all():
                if t.language == 'es':
                    texto_es = t.text
                if t.language == 'pt-br':
                    texto_pt = t.text

            hc_list = [hc.code, hc.text, texto_pt, texto_es, hc.vocabulary]

            intervention_keyword_list.append(hc_list)
            if i_key_index == 3:
                break
            i_key_index =+ 1

        try:
            trial_dic['DESCRITORES_INTERVENCAO_1_PT'] = '[%s] %s: %s' % (intervention_keyword_list[0][4], intervention_keyword_list[0][0], intervention_keyword_list[0][2])
        except:
            trial_dic['DESCRITORES_INTERVENCAO_1_PT'] = except_msg

        try:
            trial_dic['DESCRITORES_INTERVENCAO_2_PT'] = '[%s] %s: %s' % (intervention_keyword_list[1][4],intervention_keyword_list[1][0], intervention_keyword_list[1][2])
        except:
            trial_dic['DESCRITORES_INTERVENCAO_2_PT'] = except_msg

        try:
            trial_dic['DESCRITORES_INTERVENCAO_3_PT'] = '[%s] %s: %s' % (intervention_keyword_list[2][4],intervention_keyword_list[2][0], intervention_keyword_list[2][2])
        except:
            trial_dic['DESCRITORES_INTERVENCAO_3_PT'] = except_msg

        try:
            trial_dic['DESCRITORES_INTERVENCAO_1_EN'] = '[%s] %s: %s' % (intervention_keyword_list[0][4],intervention_keyword_list[0][0], intervention_keyword_list[0][1])
        except:
            trial_dic['DESCRITORES_INTERVENCAO_1_EN'] = except_msg

        try:
            trial_dic['DESCRITORES_INTERVENCAO_2_EN'] = '[%s] %s: %s' % (intervention_keyword_list[1][4],intervention_keyword_list[1][0], intervention_keyword_list[1][1])
        except:
            trial_dic['DESCRITORES_INTERVENCAO_2_EN'] = except_msg

        try:
            trial_dic['DESCRITORES_INTERVENCAO_3_EN'] = '[%s] %s: %s' % (intervention_keyword_list[2][4],intervention_keyword_list[2][0], intervention_keyword_list[2][1])
        except:
            trial_dic['DESCRITORES_INTERVENCAO_3_EN'] = except_msg

        try:
            trial_dic['DESCRITORES_INTERVENCAO_1_ES'] = '[%s] %s: %s' % (intervention_keyword_list[0][4],intervention_keyword_list[0][0], intervention_keyword_list[0][3])
        except:
            trial_dic['DESCRITORES_INTERVENCAO_1_ES'] = except_msg

        try:
            trial_dic['DESCRITORES_INTERVENCAO_2_ES'] = '[%s] %s: %s' % (intervention_keyword_list[1][4],intervention_keyword_list[1][0], intervention_keyword_list[1][3])
        except:
            trial_dic['DESCRITORES_INTERVENCAO_2_ES'] = except_msg

        try:
            trial_dic['DESCRITORES_INTERVENCAO_3_ES'] = '[%s] %s: %s' % (intervention_keyword_list[2][4],intervention_keyword_list[2][0], intervention_keyword_list[2][3])
        except:
            trial_dic['DESCRITORES_INTERVENCAO_3_ES'] = except_msg

        try:
            trial_dic['SITUACAO_DO_RECRUTAMENTO'] = [t.description for t in ct.recruitment_status.translations.all() if t.language == 'pt-br'][0]
        except:
            trial_dic['SITUACAO_DO_RECRUTAMENTO'] = except_msg


        recruitment_country_list = []
        rc_index = 1
        countries = [country for country in ct.recruitment_country.all()]
        for country in countries:
            for t in country.translations.all():
                if t.language == 'pt-br':
                    recruitment_country_list.append(t.description)
            if rc_index == 4:
                break
            rc_index += 1

        try:
            trial_dic['PAIS_DE_RECRUTAMENTO_1'] = recruitment_country_list[0]
        except:
            trial_dic['PAIS_DE_RECRUTAMENTO_1'] = except_msg

        try:
            trial_dic['PAIS_DE_RECRUTAMENTO_2'] = recruitment_country_list[1]
        except:
            trial_dic['PAIS_DE_RECRUTAMENTO_2'] = except_msg

        try:
            trial_dic['PAIS_DE_RECRUTAMENTO_3'] = recruitment_country_list[2]
        except:
            trial_dic['PAIS_DE_RECRUTAMENTO_3'] = except_msg

        try:
            trial_dic['PAIS_DE_RECRUTAMENTO_4'] = recruitment_country_list[3]
        except:
            trial_dic['PAIS_DE_RECRUTAMENTO_4'] = except_msg

        try:
            trial_dic['DATA_PRIMEIRO_RECRUTAMENTO'] = ct.enrollment_start_actual
        except:
            trial_dic['DATA_PRIMEIRO_RECRUTAMENTO'] = except_msg

        try:
            trial_dic['DATA_ULTIMO_RECRUTAMENTO'] = ct.enrollment_end_planned
        except:
            trial_dic['DATA_ULTIMO_RECRUTAMENTO'] = except_msg

        try:
            trial_dic['TAMANHO_DA_AMOSTRA_ALVO'] = ct.target_sample_size
        except:
            trial_dic['TAMANHO_DA_AMOSTRA_ALVO'] = except_msg

        try:
            trial_dic['GENERO'] = [genero[1] for genero in INCLUSION_GENDER if genero[0] == ct.gender][0]
        except:
            trial_dic['GENERO'] = except_msg

        try:
            trial_dic['UNIDADE_IDADE_MAX'] = [t[1] for t in INCLUSION_AGE_UNIT if t[0] == ct.agemax_unit][0]
        except:
            trial_dic['UNIDADE_IDADE_MAX'] = except_msg

        try:
            trial_dic['IDADE_MAX'] = ct.agemax_value
        except:
            trial_dic['IDADE_MAX'] = except_msg

        try:
            trial_dic['IDADE_MIN'] = ct.agemin_value
        except:
            trial_dic['IDADE_MIN'] = except_msg

        try:
            trial_dic['UNIDADE_IDADE_MIN'] = [t[1] for t in INCLUSION_AGE_UNIT if t[0] == ct.agemin_unit][0]
        except:
            trial_dic['UNIDADE_IDADE_MIN'] = except_msg

        try:
            trial_dic['CRITERIOS_DE_INCLUSAO_PT'] = campo('inclusion_criteria', 'pt-br')
        except:
            trial_dic['CRITERIOS_DE_INCLUSAO_PT'] = except_msg

        try:
            trial_dic['CRITERIOS_DE_INCLUSAO_ES'] = campo('inclusion_criteria', 'es')
        except:
            trial_dic['CRITERIOS_DE_INCLUSAO_ES'] = except_msg

        try:
            trial_dic['CRITERIOS_DE_INCLUSAO_EN'] = ct.inclusion_criteria
        except:
            trial_dic['CRITERIOS_DE_INCLUSAO_EN'] = except_msg

        try:
            trial_dic['DESENHO_DO_ESTUDO_PT'] = campo('study_design', 'pt-br')
        except:
            trial_dic['DESENHO_DO_ESTUDO_PT'] = except_msg

        try:
            trial_dic['DESENHO_DO_ESTUDO_ES'] = campo('study_design', 'es')
        except:
            trial_dic['DESENHO_DO_ESTUDO_ES'] = except_msg

        try:
            trial_dic['DESENHO_DO_ESTUDO_EN'] = ct.study_design
        except:
            trial_dic['DESENHO_DO_ESTUDO_EN'] = except_msg

        try:
            trial_dic['PROGRAMA_DE_ACESSO'] = [t[1] for t in BOLEANO if t[0] == ct.expanded_access_program][0]
        except:
            trial_dic['PROGRAMA_DE_ACESSO'] = except_msg

        try:
            trial_dic['ENFOQUE_DO_ESTUDO'] = [t.label for t in ct.purpose.translations.all() if t.language == 'pt-br'][0]
        except:
            trial_dic['ENFOQUE_DO_ESTUDO'] = except_msg

        try:
            trial_dic['DESENHO_DA_INTERVENCAO'] = [t.label for t in ct.intervention_assignment.translations.all() if t.language == 'pt-br'][0]
        except:
            trial_dic['DESENHO_DA_INTERVENCAO'] = except_msg

        try:
            trial_dic['BRACOS'] = ct.number_of_arms
        except:
            trial_dic['BRACOS'] = except_msg

        try:
            trial_dic['MASCARAMENTO'] = [t.label for t in ct.masking.translations.all() if t.language == 'pt-br'][0]
        except:
            trial_dic['MASCARAMENTO'] = except_msg

        try:
            trial_dic['ALOCACAO'] = [t.label for t in ct.allocation.translations.all() if t.language == 'pt-br'][0]
        except:
            trial_dic['ALOCACAO'] = except_msg

        try:
            trial_dic['FASE'] = ct.phase.label
        except:
            trial_dic['FASE'] = except_msg

        try:
            trial_dic['DESENHO_ESTUDO_OBSERVACIONAL'] = [t.label for t in ct.observational_study_design.translations.all() if t.language == 'pt-br'][0]
        except:
            trial_dic['DESENHO_ESTUDO_OBSERVACIONAL'] = except_msg

        try:
            trial_dic['TEMPORALIDADE'] = [t.label for t in ct.time_perspective.translations.all() if t.language == 'pt-br'][0]
        except:
            trial_dic['TEMPORALIDADE'] = except_msg

        primary_outcome_list = []
        primary_index = 1
        po_list = []
        for po in ct.primary_outcomes():
            for t in po.translations.all():
                if t.language == 'es':
                    texto_es = t.description
                if t.language == 'pt-br':
                    texto_pt = t.description

                po_list = [po.description, texto_pt, texto_es]

            primary_outcome_list.append(po_list)
            if primary_index == 2:
                break
            primary_index =+ 1

        try:
            trial_dic['DESFECHO_PRIMARIO_1_EN'] = primary_outcome_list[0][0]
        except:
            trial_dic['DESFECHO_PRIMARIO_1_EN'] = except_msg
        try:
            trial_dic['DESFECHO_PRIMARIO_2_EN'] = primary_outcome_list[1][0]
        except:
            trial_dic['DESFECHO_PRIMARIO_2_EN'] = except_msg

        try:
            trial_dic['DESFECHO_PRIMARIO_1_PT'] = primary_outcome_list[0][1]
        except:
            trial_dic['DESFECHO_PRIMARIO_1_PT'] = except_msg
        try:
            trial_dic['DESFECHO_PRIMARIO_2_PT'] = primary_outcome_list[1][1]
        except:
            trial_dic['DESFECHO_PRIMARIO_2_PT'] = except_msg

        try:
            trial_dic['DESFECHO_PRIMARIO_1_ES'] = primary_outcome_list[0][2]
        except:
            trial_dic['DESFECHO_PRIMARIO_1_ES'] = except_msg
        try:
            trial_dic['DESFECHO_PRIMARIO_2_ES'] = primary_outcome_list[1][2]
        except:
            trial_dic['DESFECHO_PRIMARIO_2_ES'] = except_msg

            
        secondary_outcome_list = []
        secondary_index = 1
        so_list = []
        for outcomes in ct.secondary_outcomes():
            for t in outcomes.translations.all():
                if t.language == 'pt-br':
                    texto_pt = t.description
                if t.language == 'es':
                    texto_es = t.description

                so_list = [outcomes.description, texto_pt, texto_es]

            secondary_outcome_list.append(so_list)
            if secondary_index == 3:
                break
            secondary_index =+ 1

        try:
            trial_dic['DESFECHO_SECUNDARIO_1_EN'] = secondary_outcome_list[0][0]
        except:
            trial_dic['DESFECHO_SECUNDARIO_1_EN'] = except_msg
        try:
            trial_dic['DESFECHO_SECUNDARIO_2_EN'] = secondary_outcome_list[1][0]
        except:
            trial_dic['DESFECHO_SECUNDARIO_2_EN'] = except_msg

        try:
            trial_dic['DESFECHO_SECUNDARIO_1_PT'] = secondary_outcome_list[0][1]
        except:
            trial_dic['DESFECHO_SECUNDARIO_1_PT'] = except_msg
        try:
            trial_dic['DESFECHO_SECUNDARIO_2_PT'] = secondary_outcome_list[1][1]
        except:
            trial_dic['DESFECHO_SECUNDARIO_2_PT'] = except_msg

        try:
            trial_dic['DESFECHO_SECUNDARIO_1_ES'] = secondary_outcome_list[0][2]
        except:
            trial_dic['DESFECHO_SECUNDARIO_1_ES'] = except_msg
        try:
            trial_dic['DESFECHO_SECUNDARIO_2_ES'] = secondary_outcome_list[1][2]
        except:
            trial_dic['DESFECHO_SECUNDARIO_2_ES'] = except_msg

        try:
            trial_dic['LOGIN'] = ct.submission.creator
        except:
            trial_dic['LOGIN'] = except_msg

        if ct.status == 'processing':
            try:
                trial_dic['STATUS'] = ct.submission.status
            except:
                trial_dic['STATUS'] = ct.status
        else:
            trial_dic['STATUS'] = ct.status

        try:
            trial_dic['EMAIL'] = ct.submission.creator.email
        except:
            trial_dic['EMAIL'] = except_msg

        trial_dic_list.append(trial_dic)

    return trial_dic_list


def xml_opentrials(trials, include_translations=True, **kwargs):
    """Generates an Opentrials XML for a given Clinical Trial and returns as string."""
    prepared_trials = []
    for trial in trials:
        for translation in trial.translations:
            translation['primary_outcomes'] = []
            for outcome in trial.primary_outcomes:
                for out_trans in outcome['translations']:
                    if out_trans['language'] == translation['language']:
                        translation['primary_outcomes'].append(out_trans)

            translation['secondary_outcomes'] = []
            for outcome in trial.secondary_outcomes:
                for out_trans in outcome['translations']:
                    if out_trans['language'] == translation['language']:
                        translation['secondary_outcomes'].append(out_trans)

        persons = set(trial.scientific_contact + trial.public_contact + trial.site_contact)

        prepared_trials.append( (trial, persons) )

    return render_to_string(
            'repository/xml/xml_opentrials.xml',
            {'object_list': prepared_trials,
             'default_language':settings.DEFAULT_SUBMISSION_LANGUAGE,
             'reg_name': settings.REG_NAME,
             'include_translations': include_translations,
             'opentrials_xml_version': OPENTRIALS_XML_VERSION},
            )

MOD_TEMPLATE = """<!-- ===========================================================================
File: opentrials-vocabularies.mod

OpenTrials: Latin-American and Caribbean Clinical Trial Record XML DTD
DTD Version 1.0: %(generation)s

Entity definitions used by the opentrials.dtd file.
This file should be generated automatically from controlled vocabulary data
such as those from Vocabulary application.
=========================================================================== -->

%(entities)s"""

def xml_opentrials_mod(**kwargs):
    """Generates the MOD file with valid vocabularies for Opentrials XML standard."""
    entities = []

    # Languages
    #entities.append('\n'.join([
    #        '<!ENTITY % language.options',
    #        '    "en|es|fr|pt|other">'
    #        ]))

    # Health conditions
    entities.append('\n'.join([
            '<!-- TRDS 12: health condition attributes -->',
            '<!ENTITY % vocabulary.options',
            '    "decs|icd10|other">',
            ]))

    # Intervention codes
    icodes = map(prep_label_for_xml, InterventionCode.objects.values_list('label', flat=True))
    entities.append('\n'.join([
            '<!-- TRDS 13: intervention descriptor attributes -->',
            '<!-- attribute options cannot contain slashes "/" -->',
            '<!ENTITY % interventioncode.options',
            '    "%s">' % '|'.join(icodes), # FIXME: check why labels were defined with
                                            # '-' replacing ' ' on old .mod
            ]))

    # Study statuses
    statuses = map(prep_label_for_xml, RecruitmentStatus.objects.values_list('label', flat=True))
    entities.append('\n'.join([
            '<!ENTITY % requirementstatus.options',
            '    "%s">' % '|'.join(statuses),
            ]))

    # Age units
    entities.append('\n'.join([
            '<!ENTITY % ageunit.options',
            '    "null|years|months|weeks|days|hours">',
            ]))

    # Genders
    entities.append('\n'.join([
            '<!ENTITY % gender.options',
            '    "female|male|both">',
            ]))

    # Purposes
    purposes = map(prep_label_for_xml, StudyPurpose.objects.values_list('label', flat=True))
    entities.append('\n'.join([
            '<!-- TRDS 15b: study_design attributes -->',
            '<!ENTITY % purpose.options',
            '    "%s">' % '|'.join(purposes),
            ]))

    # Assignment
    assignments = map(prep_label_for_xml, InterventionAssigment.objects.values_list('label', flat=True))
    entities.append('\n'.join([
            '<!ENTITY % assignment.options',
            '    "%s">' % '|'.join(assignments),
            ]))

    # Masking
    maskings = map(prep_label_for_xml, StudyMasking.objects.values_list('label', flat=True))
    entities.append('\n'.join([
            '<!ENTITY % masking.options',
            '    "%s">' % '|'.join(maskings),
            ]))

    # Allocation
    allocations = map(prep_label_for_xml, StudyAllocation.objects.values_list('label', flat=True))
    entities.append('\n'.join([
            '<!ENTITY % allocation.options',
            '    "%s">' % '|'.join(allocations),
            ]))

    # Phases
    phases = map(prep_label_for_xml, StudyPhase.objects.values_list('label', flat=True))
    entities.append('\n'.join([
            '<!-- TRDS 15c -->',
            '<!ENTITY % phase.options',
            '    "%s">' % '|'.join(phases), # FIXME: replace N/A for null?
            ]))

    # Contact types
    entities.append('\n'.join([
            '<!ENTITY % contacttype.options',
            '    "public|scientific|site">',
            ]))

    # Countries
    countries = CountryCode.objects.values_list('label', flat=True)
    entities.append('\n'.join([
            '<!ENTITY % country.options',
            '    "%s">' % '|'.join(countries),
            ]))

    # Trial Statuses
    statuses = [st[0] for st in choices.TRIAL_RECORD_STATUS]
    entities.append('\n'.join([
            '<!ENTITY % trialstatus.options',
            '    "%s">' % '|'.join(statuses),
            ]))

    # Study Types
    study_types = map(prep_label_for_xml, StudyType.objects.values_list('label', flat=True))
    entities.append('\n'.join([
            '<!ENTITY % study_type.options',
            '    "%s">' % '|'.join(study_types),
            ]))

    # Institution Types
    institution_types = map(prep_label_for_xml, InstitutionType.objects.values_list('label', flat=True))
    entities.append('\n'.join([
            '<!ENTITY % institution_type.options',
            '    "%s">' % '|'.join(institution_types),
            ]))

    return MOD_TEMPLATE%{
            'generation': datetime.date.today().strftime('%Y-%m-%d'),
            'entities': '\n\n'.join(entities),
            }


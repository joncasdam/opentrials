# coding: utf-8

try:
    set
except:
    from sets import Set as set

from django.core import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.shortcuts import render_to_response, get_object_or_404
from django.utils.translation import ugettext_lazy as _
from django.forms.models import inlineformset_factory
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.template import loader
from django.db.models import Q
from django.views.generic.list_detail import object_list
from django.conf import settings
from django.template.defaultfilters import slugify
from django.template.context import RequestContext
from django.contrib.sites.models import Site
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.contrib import messages
from django.utils.translation import get_language
from django.utils.encoding import smart_str, smart_unicode

from reviewapp.models import Attachment, Submission, Remark
from reviewapp.models import STATUS_PENDING, STATUS_RESUBMIT, STATUS_DRAFT, STATUS_APPROVED
from reviewapp.forms import ExistingAttachmentForm,NewAttachmentForm, XmlPlataformaBrasilForm
from reviewapp.consts import STEP_STATES, REMARK, MISSING, PARTIAL, COMPLETE
from reviewapp.views import submission_edit_published, send_opentrials_email

from repository.trial_validation import trial_validator
from repository.models import ClinicalTrial, Descriptor, TrialNumber
from repository.models import TrialSecondarySponsor, TrialSupportSource, Outcome
from repository.models import PublicContact, ScientificContact, SiteContact, Contact, Institution
from repository.models import ClinicalTrialTranslation
from repository.trds_forms import MultilingualBaseFormSet
from repository.trds_forms import GeneralHealthDescriptorForm, PrimarySponsorForm
from repository.trds_forms import SecondaryIdForm, make_secondary_sponsor_form
from repository.trds_forms import make_support_source_form, TrialIdentificationForm
from repository.trds_forms import SpecificHealthDescriptorForm, HealthConditionsForm
from repository.trds_forms import InterventionDescriptorForm, InterventionForm
from repository.trds_forms import RecruitmentForm, StudyTypeForm, PrimaryOutcomesForm
from repository.trds_forms import SecondaryOutcomesForm, make_public_contact_form
from repository.trds_forms import make_scientifc_contact_form, make_contact_form, NewInstitution
from repository.trds_forms import make_site_contact_form, TRIAL_FORMS
from vocabulary.models import RecruitmentStatus, VocabularyTranslation, CountryCode, InterventionCode
from vocabulary.models import StudyPurpose, InterventionAssigment, StudyMasking, StudyAllocation
from vocabulary.models import MailMessage, InstitutionType

from polyglot.multilingual_forms import modelformset_factory

from fossil.fields import DictKeyAttribute
from fossil.models import Fossil

from utilities import user_in_group, normalize_age, denormalize_age, getValuesFromXml, geraDicPlataformaBrasil

import datetime

import choices
import settings
import csv
import cStringIO
from zipfile import ZipFile, ZIP_DEFLATED

from logger import log_actions

EXTRA_FORMS = 1

MENU_SHORT_TITLE = [_('Trial Identif.'),
                    _('Spons.'),
                    _('Health Cond.'),
                    _('Interv.'),
                    _('Recruit.'),
                    _('Study Type'),
                    _('Outcomes'),
                    _('Contacts'),
                    _('Attachs')]
def localized_vocabulary(model_instance, language, *args):
    """
    Retrieve vocabulary in a given language

    default *args: ['pk', 'description', 'label']
    """
    if not args:
        args = ['pk', 'description', 'label']

    model_qs = model_instance.objects.all()
    localized_list = model_qs.values(*args)
    for item in localized_list:
        try:
            t = VocabularyTranslation.objects.get_translation_for_object(
                                language, model=model_instance,
                                object_id=item['pk'])
            if t.description:
                item['description'] = t.description
        except ObjectDoesNotExist:
            pass

    return localized_list

def is_outdate(ct):

    now = datetime.date.today()

    start_planned = ct.enrollment_start_planned
    end_planned = ct.enrollment_end_planned
    start_actual = ct.enrollment_start_actual
    end_actual = ct.enrollment_end_planned

    if start_planned is not None:
        start_planned = start_planned
        if start_planned < now and start_actual is None:
            return True

    if end_planned is not None:
        end_planned = end_planned
        if end_planned < now and end_actual is None:
            return True

    return False

def check_user_can_edit_trial(func):
    """
    Decorator to check if current user has permission to edit a given clinical trial
    """
    def _inner(request, trial_pk, *args, **kwargs):
        request.ct = get_object_or_404(ClinicalTrial, id=int(trial_pk))
        request.can_change_trial = True

        if request.ct.submission.status == STATUS_APPROVED:
            request.can_change_trial = False
            parsed_link = reverse(submission_edit_published, args=[trial_pk])
            message_confirm_update = unicode(_("Updating a clinical trial, a new revision process will be started. Would you like to continue?"))
            edit_trial_button_string = '<form action="%s" onsubmit="return window.confirm(\'%s\')"><input type="submit" value="%s"/> </form>' % (parsed_link,message_confirm_update,unicode(_('Update')))
            messages.warning(request, _('This trial cannot be modified because it has already been approved.%s') % edit_trial_button_string)

        # Creator can edit in statuses draft and resubmited but can view on other statuses
        elif request.user == request.ct.submission.creator:
            if request.ct.submission.status not in (STATUS_DRAFT, STATUS_RESUBMIT):
                request.can_change_trial = False
                messages.warning(request, _('You cannot modify this trial because it is being revised.'))

        elif not request.user.is_staff: # If this is a staff member...
            request.can_change_trial = False
            messages.warning(request, _('Only the creator can modify a trial.'))

            # A reviewer in status pending
            if not( request.ct.submission.status == STATUS_PENDING and
                    user_in_group(request.user, 'reviewers') ):

                resp = render_to_response(
                        '403.html',
                        {'site': Site.objects.get_current()},
                        context_instance=RequestContext(request),
                        )
                resp.status_code = 403

                return resp

        return func(request, trial_pk, *args, **kwargs)

    return _inner

@login_required
@check_user_can_edit_trial
def edit_trial_index(request, trial_pk):
    ct = request.ct

    status = ct.submission.get_status()

    if status in [REMARK, MISSING]:
        submit = False
    else:
        submit = request.can_change_trial

    if request.method == 'POST':
        if submit:
            sub = ct.submission
            sub.status = STATUS_PENDING
            
            #recepient = ct.submission.creator.email
            #subject = _('Trial Submitted')
            #message =  MailMessage.objects.get(label='submitted').description
            #if '%s' in message:
            #    message = message % ct.public_title
            #send_opentrials_email(subject, message, recepient)

            sub.save()
            return HttpResponseRedirect(reverse('reviewapp.dashboard'))

        if 'xmlpb' in request.FILES:
            xml_file = request.FILES['xmlpb']

            form = XmlPlataformaBrasilForm(request.POST, files=request.FILES)
            if form.is_valid():
                from django.core.files.storage import default_storage
                from django.core.files.base import ContentFile
                import os
                import ast
                import re
                from django.template.defaultfilters import slugify

                xml_file_name = xml_file.name
                fname, dot, extension = xml_file_name.rpartition('.')
                fname = slugify(fname)
                
                destino = settings.ATTACHMENTS_PATH + '/' + '%s.%s' % (fname, extension)

                path = default_storage.save(destino, ContentFile(xml_file.read()))
                
                dicXML = geraDicPlataformaBrasil(path, choices.XMLPB)

                entry_status = Submission.objects.get(trial=ct.id)
                dic_status = ast.literal_eval(entry_status.fields_status)

                Recruitment_status = None
                TrialIdentification_status = None
                StudyType_status = None
                Interventions_status = None
                HealthConditions_status = None

                imported_list = []

                entry = ClinicalTrial.objects.get(pk=ct.pk)

                if 'target_size' in dicXML and dicXML['target_size'] != '':
                    try:
                        entry.target_sample_size = dicXML['target_size']
                        entry.save()
                        Recruitment_status = True
                        imported_list.append('Target Sample Size')
                    except:
                        print 'Error: target_size'
                
                if 'agemin' in dicXML and dicXML['agemin'] != '':
                    try: 
                        agemin = re.findall(r"\d+", dicXML['agemin'])[0]
                        entry.agemin_value = agemin
                        entry.save()
                        Recruitment_status = True
                        imported_list.append('Inclusion Minimum Age')
                    except:
                        print 'Error: agemin'

                if 'agemax' in dicXML and dicXML['agemax'] != '':
                    try:
                        agemax = re.findall(r"\d+", dicXML['agemax'])[0]
                        entry.agemax_value = agemax
                        entry.save()
                        Recruitment_status = True
                        imported_list.append('Inclusion Maximum Age')
                    except:
                        print 'Error: agemax'

                entry_translations = ClinicalTrialTranslation.objects.get(object_id=ct.pk,language__exact='pt-br')

                if 'public_title' in dicXML and dicXML['public_title'] != '':
                    try:
                        entry_translations.public_title = dicXML['public_title']
                        entry_translations.save()
                        TrialIdentification_status = True
                        imported_list.append('Public Title')
                    except:
                        print 'Error: public_title'

                if 'acronym' in dicXML and dicXML['acronym'] != '':
                    try:
                        entry_translations.acronym = dicXML['acronym']
                        entry_translations.save()
                        TrialIdentification_status = True
                        imported_list.append('Acronym')
                    except:
                        print 'Error: acronym'

                if 'scientific_title' in dicXML and dicXML['scientific_title'] != '':
                    try:
                        entry_translations.scientific_title = dicXML['scientific_title']
                        entry_translations.save()
                        TrialIdentification_status = True
                        imported_list.append('Scientific Title')
                    except:
                        print 'Error: scientific_title'

                if 'study_design' in dicXML and dicXML['study_design'] != '':
                    try:
                        entry_translations.study_design = dicXML['study_design']
                        entry_translations.save()
                        StudyType_status = True
                        imported_list.append('Study Design')
                    except:
                        print 'Error: study_design'

                if 'scientific_acronym' in dicXML and dicXML['scientific_acronym'] != '':
                    try:
                        entry_translations.scientific_acronym = dicXML['scientific_acronym']
                        entry_translations.save()
                        TrialIdentification_status = True
                        imported_list.append('Scientific Acronym')
                    except:
                        print 'Error: scientific_acronym'

                if 'inclusion_criteria' in dicXML and dicXML['inclusion_criteria'] != '':
                    try:
                        entry_translations.inclusion_criteria = dicXML['inclusion_criteria']
                        entry_translations.save()
                        Recruitment_status = True
                        imported_list.append('Inclusion Criteria')
                    except:
                        print 'Error: inclusion_criteria'

                if 'hc_freetext' in dicXML and dicXML['hc_freetext'] != '':
                    try:
                        entry_translations.hc_freetext = dicXML['hc_freetext']
                        entry_translations.save()
                        HealthConditions_status = True
                        imported_list.append('Health Condition(s)')
                    except:
                        print 'Error: hc_freetext'

                if 'i_freetext' in dicXML and dicXML['i_freetext'] != '':
                    try:
                        entry_translations.i_freetext = dicXML['i_freetext']
                        entry_translations.save()
                        Interventions_status = True
                        imported_list.append('Intervention(s)')
                    except:
                        print 'Erro: i_freetext'

                if 'exclusion_criteria' in dicXML and dicXML['exclusion_criteria'] != '':
                    try:
                        entry_translations.exclusion_criteria = dicXML['exclusion_criteria']
                        entry_translations.save()
                        Recruitment_status = True
                        imported_list.append('Exclusion Criteria')
                    except:
                        print 'Erro: exclusion_criteria'

                # update Trial status
                from django.utils import simplejson
                if Recruitment_status: dic_status['pt-br']['Recruitment'] = 3

                if TrialIdentification_status: dic_status['pt-br']['Trial Identification'] = 3
                
                if StudyType_status: dic_status['pt-br']['Study Type'] = 3
                
                if Interventions_status: dic_status['pt-br']['Interventions'] = 3
                
                if HealthConditions_status: dic_status['pt-br']['Health Conditions'] = 3

                entry_status.fields_status = unicode(simplejson.dumps(dic_status))
                entry_status.save()

                # return HttpResponseRedirect(reverse('reviewapp.dashboard'))

                return render_to_response('repository/xmlpb.html',
                                  {'trial_pk':ct.id,
                                    'imported_fields':imported_list,},
                                   context_instance=RequestContext(request))
    else:
        ''' start view '''
        form = XmlPlataformaBrasilForm()

        # Changes status from "resubmit" to "draft" if user is the creator
        sub = ct.submission
        if sub.status == STATUS_RESUBMIT and request.user == sub.creator:
            sub.status = STATUS_DRAFT
            sub.save()

        fields_status = ct.submission.get_fields_status()

        links = []
        for i, name in enumerate(TRIAL_FORMS):
            data = dict(label=_(name))
            data['url'] = reverse('step_' + str(i + 1), args=[trial_pk])

            trans_list = []
            for lang in fields_status:
                trans = {}
                lang = lang.lower()
                step_status = fields_status.get(lang, {}).get(name, None)
                if step_status == MISSING:
                    trans['icon'] = settings.MEDIA_URL + 'images/form-status-missing.png'
                    trans['msg'] = STEP_STATES[MISSING-1][1].title()
                    trans['leg'] = _("There are required fields missing.")
                elif step_status == PARTIAL:
                    trans['icon'] = settings.MEDIA_URL + 'images/form-status-partial.png'
                    trans['msg'] = STEP_STATES[PARTIAL-1][1].title()
                    trans['leg'] = _("All required fields were filled.")
                elif step_status == COMPLETE:
                    trans['icon'] = settings.MEDIA_URL + 'images/form-status-complete.png'
                    trans['msg'] = STEP_STATES[COMPLETE-1][1].title()
                    trans['leg'] = _("All fields were filled.")
                elif step_status == REMARK:
                    trans['icon'] = settings.MEDIA_URL + 'images/form-status-remark.png'
                    trans['msg'] = STEP_STATES[REMARK-1][1].title()
                    trans['leg'] = _("There are fields with remarks.")
                else:
                    trans['icon'] = settings.MEDIA_URL + 'media/img/admin/icon_error.gif'
                    trans['msg'] = _('Error')
                    trans['leg'] = _('Error')

                trans_list.append(trans)
            data['trans'] = trans_list
            links.append(data)

        status_message = {}
        if status == REMARK:
            status_message['icon'] = settings.MEDIA_URL + 'images/form-status-remark.png'
            status_message['msg'] = _("There are fields with remarks.")
        elif status == MISSING:
            status_message['icon'] = settings.MEDIA_URL + 'images/form-status-missing.png'
            status_message['msg'] = _("There are required fields missing.")
        elif status == PARTIAL:
            status_message['icon'] = settings.MEDIA_URL + 'images/form-status-partial.png'
            status_message['msg'] = _("All required fields were filled.")
        elif status == COMPLETE:
            status_message['icon'] = settings.MEDIA_URL + 'images/form-status-complete.png'
            status_message['msg'] = _("All fields were filled.")
        else:
            status_message['icon'] = settings.MEDIA_URL + 'media/img/admin/icon_error.gif'
            status_message['msg'] = _("Error")


        return render_to_response('repository/trial_index.html',
                                  {'trial_pk':trial_pk,
                                   'submission':ct.submission,
                                   'links':links,
                                   'status': status,
                                   'form_xmlpb': form,
                                   'submit': submit,
                                   'status_message': status_message,},
                                   context_instance=RequestContext(request))

def full_view(request, trial_pk):
    ''' full view '''
    ct = get_object_or_404(ClinicalTrial, id=int(trial_pk))
    return render_to_response('repository/trds.html',
                              {'fieldtable':ct.html_dump()},
                               context_instance=RequestContext(request))


def recruiting(request):
    ''' List all registered trials with recruitment_status = recruiting
    '''
    object_list = ClinicalTrial.fossils.recruiting()
    object_list = object_list.proxies(language=request.LANGUAGE_CODE)

    """
    recruitments = RecruitmentStatus.objects.filter(label__exact='recruiting')
    if len(recruitments) > 0:
        object_list = ClinicalTrial.published.filter(recruitment_status=recruitments[0])
    else:
        object_list = None

    for obj in object_list:
        try:
            trans = obj.translations.get(language__iexact=request.LANGUAGE_CODE)
        except ClinicalTrialTranslation.DoesNotExist:
            trans = None

        if trans:
            if trans.public_title:
                obj.public_title = trans.public_title
            if trans.public_title:
                obj.scientific_title = trans.scientific_title

        if obj.recruitment_status:
            try:
                rec_status_trans = obj.recruitment_status.translations.get(language__iexact=request.LANGUAGE_CODE)
            except VocabularyTranslation.DoesNotExist:
                rec_status_trans = obj.recruitment_status
            obj.rec_status = rec_status_trans.label
    """

    # pagination
    paginator = Paginator(object_list, getattr(settings, 'PAGINATOR_CT_PER_PAGE', 10))

    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    try:
        objects = paginator.page(page)
    except (EmptyPage, InvalidPage):
        objects = paginator.page(paginator.num_pages)


    return render_to_response('repository/clinicaltrial_recruiting.html',
                              {'objects': objects,
                               'page': page,
                               'paginator': paginator},
                               context_instance=RequestContext(request))

#Applied Search Criteria
def get_humanizer(language_code, min_age_unit, max_age_unit):

    def humanize_search_values(key, value, default_str=None):
        """
        This function is used to translate advanced search params
        into formatted values ready to print in templates.

        If a key/value is unknown, a default string is returned.
        """
        if default_str is None:
            default_str = '###unknown search parameters###'

        age_unit_labels = {
            'Y':_('years'),
            'M':_('months'),
            'W':_('weeks'),
            'D':_('days'),
            'H':_('hours'),
        }

        if key == 'rec_country':
            humanized = [_('Recruitment Country')]

            for country in localized_vocabulary(CountryCode, language_code):
                if country['label'] == value:
                    humanized.append(country['description'])
                    break
            else:
                humanized.append(default_str)
            return humanized

        elif key == 'rec_status_exact':
            humanized = [_('Recruitment Status')]

            statuses = []
            for status in localized_vocabulary(RecruitmentStatus, language_code):
                if status['label'] in value:
                    statuses.append(status['description'])
            humanized.append(', '.join(statuses) if statuses else default_str)
            return humanized

        elif key == 'is_observational':
            humanized = [_('Study Type')]

            if value not in ['true','false']:
                humanized.append(default_str)
            else:
                humanized.append(_('Observational') if value == 'true' else _('Interventional'))
            return humanized

        elif key == 'i_type_exact':
            humanized = [_('Institution type')]

            i_types = []
            for i_type in localized_vocabulary(InstitutionType, language_code):
                if i_type['label'] in value:
                    i_types.append(i_type['description'])
            humanized.append(', '.join(i_types) if i_types else default_str)
            return humanized

        elif key == 'gender':
            humanized = [_('Inclusion Gender')]

            if value in ['male', 'female', 'both']:
                humanized.append(_(value))
            else:
                humanized.append(default_str)
            return humanized
        elif key == 'maximum_recruitment_age__gte':
            #due to the logic applied to the query, the key names are inverted (min an max age)
            #see the index view callable
            humanized = [_('Inclusion Minimum Age')]
            try:
                humanized.append(u'%s %s' % (denormalize_age(value, min_age_unit), age_unit_labels[min_age_unit]))
            except KeyError:
                humanized.append(u'%s %s' % (denormalize_age(value, 'Y'), age_unit_labels['Y']))
            return humanized
        elif key == 'minimum_recruitment_age__lte':
            #due to the logic applied to the query, the key names are inverted (min an max age)
            #see the index view callable
            humanized = [_('Inclusion Maximum Age')]
            try:
                humanized.append(u'%s %s' % (denormalize_age(value, max_age_unit), age_unit_labels[max_age_unit]))
            except KeyError:
                humanized.append(u'%s %s' % (denormalize_age(value, 'Y'), age_unit_labels['Y']))
            return humanized
        else:
            return [key, default_str]

    return humanize_search_values

def index(request):
    ''' List all registered trials
        If you use a search term, the result is filtered
    '''
    q = request.GET.get('q', '').strip()
    rec_status = request.GET.getlist('rec_status')
    rec_country = request.GET.get('rec_country', '').strip()
    is_observational = request.GET.get('is_observ', '').strip()
    i_type = request.GET.getlist('i_type')
    gender = request.GET.get('gender', '').strip()
    minimum_age = request.GET.get('age_min','').strip()
    maximum_age = request.GET.get('age_max','').strip()
    minimum_age_unit = request.GET.get('age_min_unit','').strip()
    maximum_age_unit = request.GET.get('age_max_unit','').strip()

    filters = {}
    if rec_status:
        filters['rec_status_exact'] = rec_status
    if rec_country:
        filters['rec_country'] = rec_country
    if is_observational:
        filters['is_observational'] = is_observational
    if i_type:
        filters['i_type_exact'] = i_type
    if gender:
        filters['gender'] = gender

    #query by age logic explained at http://reddes.bvsalud.org/projects/clinical-trials/wiki/InclusionCriteriaField
    if minimum_age:
        try:
            filters['maximum_recruitment_age__gte'] = normalize_age(int(minimum_age),minimum_age_unit)
        except (ValueError, KeyError):
            filters['maximum_recruitment_age__gte'] = 0
    if maximum_age:
        try:
            filters['minimum_recruitment_age__lte'] = normalize_age(int(maximum_age),maximum_age_unit)
        except (ValueError, KeyError):
            filters['minimum_recruitment_age__lte'] = normalize_age(200, 'Y')


    object_list = ClinicalTrial.fossils.published_advanced(q=q, **filters)
    unsubmiteds = Submission.objects.filter(title__icontains=q).filter(Q(status='draft') | Q(status='resubmit')).order_by('-updated')
    object_list = object_list.proxies(language=request.LANGUAGE_CODE)
    paginator = Paginator(object_list, getattr(settings, 'PAGINATOR_CT_PER_PAGE', 10))

    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    try:
        objects = paginator.page(page)
    except (EmptyPage, InvalidPage):
        objects = paginator.page(paginator.num_pages)

    search_humanizer = get_humanizer(request.LANGUAGE_CODE.lower(), minimum_age_unit, maximum_age_unit)
    search_filters = [search_humanizer(k, v)
                        for k, v in filters.items() if v]
    
    return render_to_response('repository/clinicaltrial_list.html',
                              {'objects': objects,
                               'page': page,
                               'paginator': paginator,
                               'q': q,
                               'unsubmiteds':unsubmiteds,
                               'outdated_flag':settings.MEDIA_URL + 'media/img/admin/icon_error.gif',
                               'search_filters': dict(search_filters),
                               },
                               context_instance=RequestContext(request))

@login_required
def trial_view(request, trial_pk):
    ''' show details of a trial of a user logged '''
    ct = get_object_or_404(ClinicalTrial, id=int(trial_pk))
            
    if ct.submission.status == STATUS_DRAFT and not request.user.is_staff:
        req = ''
    else:
        req, space, title = str(ct).partition(' ')

    review_mode = True
    if not request.user.is_staff and not user_in_group(request.user, 'reviewers'):

        review_mode = False
        if request.user != ct.submission.creator:
            return render_to_response('403.html', {'site': Site.objects.get_current(),},
                            context_instance=RequestContext(request))

    if review_mode:
        can_approve = ct.submission.status == STATUS_PENDING and ct.submission.remark_set.exclude(status='closed').count() == 0
        can_resubmit = ct.submission.status == STATUS_PENDING
        is_ct_author = ct.submission.creator
    else:
        can_approve = False
        can_resubmit = False

    translations = [t for t in ct.translations.all()]
    remark_list = []
    for tf in TRIAL_FORMS:
         remarks = ct.submission.remark_set.filter(context=slugify(tf))
         if remarks:
            remark_list.append(remarks)

    # get translation for recruitment status
    recruitment_status = ct.recruitment_status
    if recruitment_status:
        recruitment_label = recruitment_status.label
        try:
            t = VocabularyTranslation.objects.get_translation_for_object(
                                request.LANGUAGE_CODE.lower(), model=RecruitmentStatus,
                                object_id=recruitment_status.id)
            if t.label:
                recruitment_label = t.label
        except ObjectDoesNotExist:
            pass
    else:
        recruitment_label = ""

    # get translations for recruitment country
    recruitment_country = ct.recruitment_country.all()
    recruitment_country_list = recruitment_country.values('pk', 'description')
    for obj in recruitment_country_list:
        try:
            t = VocabularyTranslation.objects.get_translation_for_object(
                                request.LANGUAGE_CODE.lower(), model=CountryCode,
                                object_id=obj['pk'])
            if t.description:
                obj['description'] = t.description
        except ObjectDoesNotExist:
            pass

    # get translations for scientific contacts country
    scientific_contacts = ct.scientific_contacts()
    scientific_contacts_list = scientific_contacts.values('pk', 'firstname', 'middlename',
                            'lastname', 'address', 'city', 'zip', 'country_id', 'telephone',
                            'email', 'affiliation__name')

    for obj in scientific_contacts_list:
        try:
            country = CountryCode.objects.get(pk=obj['country_id'])
            obj['country_description'] = country.description
        except CountryCode.DoesNotExist:
            obj['country_description'] = ""

        try:
            t = VocabularyTranslation.objects.get_translation_for_object(
                                request.LANGUAGE_CODE.lower(), model=CountryCode,
                                object_id=obj['country_id'])
            if t.description:
                obj['country_description'] = t.description
        except ObjectDoesNotExist:
            pass

    # get translations for public contacts country
    public_contacts = ct.public_contacts()
    public_contacts_list = public_contacts.values('pk', 'firstname', 'middlename',
                            'lastname', 'address', 'city', 'zip', 'country_id', 'telephone',
                            'email', 'affiliation__name')

    for obj in public_contacts_list:
        try:
            country = CountryCode.objects.get(pk=obj['country_id'])
            obj['country_description'] = country.description
        except CountryCode.DoesNotExist:
            obj['country_description'] = ""

        try:
            t = VocabularyTranslation.objects.get_translation_for_object(
                                request.LANGUAGE_CODE.lower(), model=CountryCode,
                                object_id=obj['country_id'])
            if t.description:
                obj['country_description'] = t.description
        except ObjectDoesNotExist:
            pass

    # get translations for site contacts country
    site_contacts = ct.site_contact.all().select_related()
    site_contacts_list = site_contacts.values('pk', 'firstname', 'middlename',
                            'lastname', 'address', 'city', 'zip', 'country_id', 'telephone',
                            'email', 'affiliation__name')

    for obj in site_contacts_list:
        try:
            country = CountryCode.objects.get(pk=obj['country_id'])
            obj['country_description'] = country.description
        except CountryCode.DoesNotExist:
            obj['country_description'] = ""

        try:
            t = VocabularyTranslation.objects.get_translation_for_object(
                                request.LANGUAGE_CODE.lower(), model=CountryCode,
                                object_id=obj['country_id'])
            if t.description:
                obj['country_description'] = t.description
        except ObjectDoesNotExist:
            pass

    enrollment_start_date = ct.enrollment_start_actual if \
        ct.enrollment_start_actual is not None else ct.enrollment_start_planned
    enrollment_end_date = ct.enrollment_end_actual if \
        ct.enrollment_end_actual is not None else ct.enrollment_end_planned
    
    if ct.language != 'pt-br':
        try:
            allocation_type = ct.allocation.label
            masking_type = ct.masking.label
            intervention_assigment = ct.intervention_assignment.label
            purpose = ct.purpose.label
            expanded_access_program = str(ct.expanded_access_program)
        except:
            allocation_type = ''
            masking_type = ''
            intervention_assigment = ''
            purpose = ''
            expanded_access_program = ''


    else:
        allocation_type = ''
        masking_type = ''
        intervention_assigment = ''
        purpose = ''
        expanded_access_program = ''

    try:
        public_title = [t.public_title for t in translations
                if t.language == get_language() and t.public_title.strip()][0]
    except IndexError:
        public_title = ct.public_title

    try:
        scientific_title = [t.scientific_title for t in translations
                if t.language == get_language() and t.scientific_title.strip()][0]
    except IndexError:
        scientific_title = ct.scientific_title
        
    return render_to_response('repository/clinicaltrial_detail_user.html',
                                {'object': ct,
                                'req': req,
                                'ct_l': ct.language,
                                'allocation_type': allocation_type,
                                'masking_type': masking_type,
                                'intervention_assigment': intervention_assigment,
                                'purpose': purpose,
                                'expanded_access_program': expanded_access_program,
                                'translations': translations,
                                'host': request.get_host(),
                                'remark_list': remark_list,
                                'review_mode': review_mode,
                                'can_approve': can_approve,
                                'can_resubmit': can_resubmit,
                                'languages': get_sorted_languages(request),
                                'recruitment_label': recruitment_label,
                                'recruitment_country': recruitment_country_list,
                                'scientific_contacts': scientific_contacts_list,
                                'public_contacts': public_contacts_list,
                                'site_contacts': site_contacts_list,
                                'enrollment_start_date': enrollment_start_date,
                                'public_title': public_title,
                                'scientific_title': scientific_title,
                                'enrollment_end_date': enrollment_end_date,
                                },
                                context_instance=RequestContext(request))

def get_sorted_languages(request):
    # This just copy managed languages to sorte with main language first
    languages = [lang.lower() for lang in settings.MANAGED_LANGUAGES]
    languages.sort(lambda a,b: -1 if a == request.trials_language else cmp(a,b))
    return languages

def trial_registered(request, trial_fossil_id, trial_version=None):
    ''' show details of a trial registered '''
    try:
        fossil = Fossil.objects.get(pk=trial_fossil_id)
    except Fossil.DoesNotExist:
        try:
            qs = Fossil.objects.indexed(trial_id=trial_fossil_id)
            if trial_version:
                fossil = qs.get(revision_sequential=trial_version)
            else:
                fossil = qs.get(is_most_recent=True)
        except Fossil.DoesNotExist:
            raise Http404

    ct = fossil.get_object_fossil()
    ct.fossil['language'] = ct.fossil.get('language', settings.DEFAULT_SUBMISSION_LANGUAGE)
    ct._language = ct.language
    ct.hash_code = fossil.pk
    ct.previous_revision = fossil.previous_revision
    try:
        ct.previous_revision_sequencial = fossil.previous_revision.revision_sequential
    except:
        ct.previous_revision_sequencial = None

    ct.version = fossil.revision_sequential

    translations = [ct.fossil] # the Fossil dictionary must be one of the translations
    translations.extend(ct.translations)
    try:
        scientific_title = [t['scientific_title'] for t in translations
                if t['language'] == get_language() and t['scientific_title'].strip()][0]
    except IndexError:
        scientific_title = ct.scientific_title

    created = datetime.datetime.strptime(ct.fossil['created'], "%Y-%m-%d %H:%M:%S")

    if len(trial_fossil_id) == 64:
        trial_fossil_id = unicode(fossil).split(' ')[0]

    trial = get_object_or_404(ClinicalTrial, trial_id=trial_fossil_id)
    attachs = [attach for attach in trial.trial_attach() if attach.public]

    if ct.language != 'pt-br':
        allocation_type = ct.allocation.label
        masking_type = ct.masking.label
        intervention_assigment = ct.intervention_assignment.label
        purpose = ct.purpose.label
        expanded_access_program = str(ct.expanded_access_program)
    else:
        allocation_type = ''
        masking_type = ''
        intervention_assigment = ''
        purpose = ''
        expanded_access_program = ''

    try:
        time_perspective = trial.time_perspective
    except ObjectDoesNotExist:
        time_perspective = None
    observational_study_design = trial.observational_study_design

    return render_to_response('repository/clinicaltrial_detail_published.html',
                                {'object': ct,
                                'ct_l': ct.language,
                                'allocation_type': allocation_type,
                                'masking_type': masking_type,
                                'intervention_assigment': intervention_assigment,
                                'purpose': purpose,
                                'expanded_access_program': expanded_access_program,
                                'attachs': attachs,
                                'translations': translations,
                                'time_perspective':time_perspective,
                                'observational_study_design':observational_study_design,
                                'host': request.get_host(),
                                'fossil_created': created,
                                'register_number': trial_fossil_id,
                                'scientific_title': scientific_title,
                                'languages': get_sorted_languages(request),
                                'outdated_flag':settings.MEDIA_URL + 'media/img/admin/icon_error.gif',
                                },
                                context_instance=RequestContext(request))

@login_required
def new_institution(request):

    if request.method == 'POST':
        new_institution = NewInstitution(request.POST)
        if new_institution.is_valid():
            institution = new_institution.save(commit=False)
            institution.creator = request.user
            institution.save()
            json = serializers.serialize('json',[institution])
            return HttpResponse(json, mimetype='application/json')
        else:
            return HttpResponse(new_institution.as_table(), mimetype='text/html')

    else:
        new_institution = NewInstitution()

    return render_to_response('repository/new_institution.html',
                             {'form':new_institution},
                               context_instance=RequestContext(request))

@login_required
def contacts(request):
    from django import forms

    if request.method == 'POST':
        if request.POST.get('contact') != '-':
            contact = Contact.objects.get(pk=request.POST.get('contact'))
            contact.delete()
            contact.save()

    choices = [('-','-----------')] + [(c.pk, c.name()) for c in Contact.objects.filter(creator=request.user)]
    class ContactsForm(forms.Form):
        contact = forms.ChoiceField(label=_('Contact'),
                                  choices=choices,
                                  )

    form = ContactsForm()

    return render_to_response('repository/delete_contact.html',
                             { 'form':form,
                               'form_title':_('Delete Contact'),
                               'title':_('Delete Contact'),},
                               context_instance=RequestContext(request))


def step_list(trial_pk):
    import sys
    current_step = int( sys._getframe(1).f_code.co_name.replace('step_','') )
    steps = []
    for i in range(1,10):
        steps.append({'link': reverse('step_%d'%i,args=[trial_pk]),
                      'is_current': (i == current_step),
                      'name': MENU_SHORT_TITLE[i-1]})
    return steps

@login_required
@check_user_can_edit_trial
def step_1(request, trial_pk):
    ct = request.ct

    if not request.user.is_staff and not user_in_group(request.user, 'reviewers'):
        if request.user != ct.submission.creator:
            return render_to_response('403.html', {'site': Site.objects.get_current(),},
                            context_instance=RequestContext(request))

    if request.method == 'POST' and request.can_change_trial:
        form = TrialIdentificationForm(request.POST, instance=ct,
                                        default_second_language=ct.submission.get_secondary_language(),
                                        display_language=request.user.get_profile().preferred_language)
        SecondaryIdSet = inlineformset_factory(ClinicalTrial, TrialNumber,
                                               form=SecondaryIdForm,
                                               extra=EXTRA_FORMS)
        secondary_forms = SecondaryIdSet(request.POST, instance=ct)

        if form.is_valid() and secondary_forms.is_valid():
            secondary_forms.save()
            form.save()
            return HttpResponseRedirect(reverse('step_1',args=[trial_pk]))
    else:
        form = TrialIdentificationForm(instance=ct,
                                       default_second_language=ct.submission.get_secondary_language(),
                                       display_language=request.user.get_profile().preferred_language,
                                       )
        SecondaryIdSet = inlineformset_factory(ClinicalTrial, TrialNumber,
                                               form=SecondaryIdForm,
                                               extra=EXTRA_FORMS, can_delete=True)
        secondary_forms = SecondaryIdSet(instance=ct)

    forms = [form]
    formsets = [secondary_forms]
    return render_to_response('repository/trial_form.html',
                              {'forms':forms,'formsets':formsets,
                               'trial_pk':trial_pk,
                               'title':TRIAL_FORMS[0],
                               'steps': step_list(trial_pk),
                               'remarks':Remark.status_open.filter(submission=ct.submission,context=slugify(TRIAL_FORMS[0])),
                               'default_second_language': ct.submission.get_secondary_language(),
                               'available_languages': [lang.lower() for lang in ct.submission.get_fields_status()],
                               },
                               context_instance=RequestContext(request))


@login_required
@check_user_can_edit_trial
def step_2(request, trial_pk):
    ct = request.ct

    if not request.user.is_staff and not user_in_group(request.user, 'reviewers'):
        if request.user != ct.submission.creator:
            return render_to_response('403.html', {'site': Site.objects.get_current(),},
                            context_instance=RequestContext(request))

    qs_primary_sponsor = Institution.objects.filter(creator=request.user).order_by('name')

    if request.method == 'POST' and request.can_change_trial:
        form = PrimarySponsorForm(request.POST, instance=ct, queryset=qs_primary_sponsor,
                                  display_language=request.user.get_profile().preferred_language)
        SecondarySponsorSet = inlineformset_factory(ClinicalTrial, TrialSecondarySponsor,
                           form=make_secondary_sponsor_form(request.user),extra=EXTRA_FORMS)
        SupportSourceSet = inlineformset_factory(ClinicalTrial, TrialSupportSource,
                           form=make_support_source_form(request.user),extra=EXTRA_FORMS)

        secondary_forms = SecondarySponsorSet(request.POST, instance=ct)
        sources_form = SupportSourceSet(request.POST, instance=ct)

        if form.is_valid() and secondary_forms.is_valid() and sources_form.is_valid():
            secondary_forms.save()
            sources_form.save()
            form.save()
        return HttpResponseRedirect(reverse('step_2',args=[trial_pk]))
    else:
        form = PrimarySponsorForm(instance=ct, queryset=qs_primary_sponsor,
                                  default_second_language=ct.submission.get_secondary_language(),
                                  display_language=request.user.get_profile().preferred_language)
        SecondarySponsorSet = inlineformset_factory(ClinicalTrial, TrialSecondarySponsor,
            form=make_secondary_sponsor_form(request.user),extra=EXTRA_FORMS, can_delete=True)
        SupportSourceSet = inlineformset_factory(ClinicalTrial, TrialSupportSource,
               form=make_support_source_form(request.user),extra=EXTRA_FORMS,can_delete=True)

        secondary_forms = SecondarySponsorSet(instance=ct)
        sources_form = SupportSourceSet(instance=ct)

    forms = [form]
    formsets = [secondary_forms,sources_form]
    return render_to_response('repository/step_2.html',
                              {'forms':forms,'formsets':formsets,
                               'trial_pk':trial_pk,
                               'title':TRIAL_FORMS[1],
                               'steps': step_list(trial_pk),
                               'remarks':Remark.status_open.filter(submission=ct.submission,context=slugify(TRIAL_FORMS[1])),
                               'default_second_language': ct.submission.get_secondary_language(),
                               'available_languages': [lang.lower() for lang in ct.submission.get_fields_status()],},
                               context_instance=RequestContext(request))


@login_required
@check_user_can_edit_trial
def step_3(request, trial_pk):
    ct = request.ct

    if not request.user.is_staff and not user_in_group(request.user, 'reviewers'):
        if request.user != ct.submission.creator:
            return render_to_response('403.html', {'site': Site.objects.get_current(),},
                            context_instance=RequestContext(request))

    GeneralDescriptorSet = modelformset_factory(Descriptor,
                                                formset=MultilingualBaseFormSet,
                                                form=GeneralHealthDescriptorForm,
                                                can_delete=True,
                                                extra=EXTRA_FORMS,
                                                extra_formset_attrs={
                                                    'default_second_language':ct.submission.get_secondary_language(),
                                                    'available_languages':[lang.lower() for lang in ct.submission.get_fields_status()],
                                                    'display_language':request.user.get_profile().preferred_language,
                                                    },
                                                )

    SpecificDescriptorSet = modelformset_factory(Descriptor,
                                                formset=MultilingualBaseFormSet,
                                                form=SpecificHealthDescriptorForm,
                                                can_delete=True,
                                                extra=EXTRA_FORMS,
                                                extra_formset_attrs={
                                                    'default_second_language':ct.submission.get_secondary_language(),
                                                    'available_languages':[lang.lower() for lang in ct.submission.get_fields_status()],
                                                    'display_language':request.user.get_profile().preferred_language,
                                                    },
                                                )

    general_qs = Descriptor.objects.filter(trial=trial_pk,
                                           aspect=choices.TRIAL_ASPECT[0][0],
                                           level=choices.DESCRIPTOR_LEVEL[0][0])

    specific_qs = Descriptor.objects.filter(trial=trial_pk,
                                           aspect=choices.TRIAL_ASPECT[0][0],
                                           level=choices.DESCRIPTOR_LEVEL[1][0])

    if request.method == 'POST' and request.can_change_trial:
        form = HealthConditionsForm(request.POST, instance=ct,
                                    display_language=request.user.get_profile().preferred_language)
        general_desc_formset = GeneralDescriptorSet(request.POST,queryset=general_qs,prefix='g')
        specific_desc_formset = SpecificDescriptorSet(request.POST,queryset=specific_qs,prefix='s')

        if form.is_valid() and general_desc_formset.is_valid() and specific_desc_formset.is_valid():
            descriptors = general_desc_formset.save(commit=False)
            descriptors += specific_desc_formset.save(commit=False)


            for descriptor in descriptors:
                descriptor.trial = ct

            general_desc_formset.save()
            specific_desc_formset.save()
            form.save()

            return HttpResponseRedirect(reverse('step_3',args=[trial_pk]))
    else:
        form = HealthConditionsForm(instance=ct,
                                    default_second_language=ct.submission.get_secondary_language(),
                                    display_language=request.user.get_profile().preferred_language)
        general_desc_formset = GeneralDescriptorSet(queryset=general_qs,prefix='g')
        specific_desc_formset = SpecificDescriptorSet(queryset=specific_qs,prefix='s')


    forms = [form]
    formsets = [general_desc_formset, specific_desc_formset]
    return render_to_response('repository/step_3.html',
                              {'forms':forms,'formsets':formsets,
                               'trial_pk':trial_pk,
                               'title':TRIAL_FORMS[2],
                               'steps': step_list(trial_pk),
                               'remarks':Remark.status_open.filter(submission=ct.submission,context=slugify(TRIAL_FORMS[2])),
                               'default_second_language': ct.submission.get_secondary_language(),
                               'available_languages': [lang.lower() for lang in ct.submission.get_fields_status()],},
                               context_instance=RequestContext(request))


@login_required
@check_user_can_edit_trial
def step_4(request, trial_pk):
    ct = request.ct

    if not request.user.is_staff and not user_in_group(request.user, 'reviewers'):
        if request.user != ct.submission.creator:
            return render_to_response('403.html', {'site': Site.objects.get_current(),},
                            context_instance=RequestContext(request))

    DescriptorFormSet = modelformset_factory(Descriptor,
                                          formset=MultilingualBaseFormSet,
                                          form=InterventionDescriptorForm,
                                          can_delete=True,
                                          extra=EXTRA_FORMS,
                                          extra_formset_attrs={
                                            'default_second_language':ct.submission.get_secondary_language(),
                                            'available_languages':[lang.lower() for lang in ct.submission.get_fields_status()],
                                            'display_language':request.user.get_profile().preferred_language,
                                            },
                                          )

    queryset = Descriptor.objects.filter(trial=trial_pk,
                                           aspect=choices.TRIAL_ASPECT[1][0],
                                           level=choices.DESCRIPTOR_LEVEL[0][0])
    if request.method == 'POST' and request.can_change_trial:
        form = InterventionForm(request.POST, instance=ct,
                                display_language=request.user.get_profile().preferred_language)
        specific_desc_formset = DescriptorFormSet(request.POST, queryset=queryset)

        if form.is_valid() and specific_desc_formset.is_valid():
            descriptors = specific_desc_formset.save(commit=False)


            for descriptor in descriptors:
                descriptor.trial = ct

            specific_desc_formset.save()
            form.save()
            return HttpResponseRedirect(reverse('step_4',args=[trial_pk]))
    else:
        form = InterventionForm(instance=ct,
                                default_second_language=ct.submission.get_secondary_language(),
                                display_language=request.trials_language)
        specific_desc_formset = DescriptorFormSet(queryset=queryset)

    forms = [form]
    formsets = [specific_desc_formset]
    return render_to_response('repository/step_4.html',
                              {'forms':forms,'formsets':formsets,
                               'trial_pk':trial_pk,
                               'title':TRIAL_FORMS[3],
                               'steps': step_list(trial_pk),
                               'remarks':Remark.status_open.filter(submission=ct.submission,context=slugify(TRIAL_FORMS[3])),
                               'default_second_language': ct.submission.get_secondary_language(),
                               'available_languages': [lang.lower() for lang in ct.submission.get_fields_status()],},
                               context_instance=RequestContext(request))


@login_required
@check_user_can_edit_trial
def step_5(request, trial_pk):
    ct = request.ct

    if not request.user.is_staff and not user_in_group(request.user, 'reviewers'):
        if request.user != ct.submission.creator:
            return render_to_response('403.html', {'site': Site.objects.get_current(),},
                            context_instance=RequestContext(request))

    if request.method == 'POST' and request.can_change_trial:
        form = RecruitmentForm(request.POST, instance=ct,
                               display_language=request.user.get_profile().preferred_language)

        if form.is_valid():
            form.save()
            ct.outdated = is_outdate(ct)
            ct.save()
            return HttpResponseRedirect(reverse('step_5',args=[trial_pk]))
    else:
        form = RecruitmentForm(instance=ct,
                               default_second_language=ct.submission.get_secondary_language(),
                               display_language=request.trials_language)

    forms = [form]

    return render_to_response('repository/trial_form.html',
                              {'forms':forms,
                               'trial_pk':trial_pk,
                               'title':TRIAL_FORMS[4],
                               'steps': step_list(trial_pk),
                               'remarks':Remark.status_open.filter(submission=ct.submission,context=slugify(TRIAL_FORMS[4])),
                               'default_second_language': ct.submission.get_secondary_language(),
                               'available_languages': [lang.lower() for lang in ct.submission.get_fields_status()],
                               },
                               context_instance=RequestContext(request))


@login_required
@check_user_can_edit_trial
def step_6(request, trial_pk):
    ct = request.ct

    if not request.user.is_staff and not user_in_group(request.user, 'reviewers'):
        if request.user != ct.submission.creator:
            return render_to_response('403.html', {'site': Site.objects.get_current(),},
                            context_instance=RequestContext(request))

    if request.method == 'POST' and request.can_change_trial:
        form = StudyTypeForm(request.POST, instance=ct,
                             display_language=request.user.get_profile().preferred_language)

        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('step_6',args=[trial_pk]))
    else:
        form = StudyTypeForm(instance=ct,
                             default_second_language=ct.submission.get_secondary_language(),
                             display_language=request.trials_language)

    forms = [form]
    return render_to_response('repository/trial_form.html',
                              {'forms':forms,
                               'trial_pk':trial_pk,
                               'title':TRIAL_FORMS[5],
                               'steps': step_list(trial_pk),
                               'remarks':Remark.status_open.filter(submission=ct.submission,context=slugify(TRIAL_FORMS[5])),
                               'default_second_language': ct.submission.get_secondary_language(),
                               'available_languages': [lang.lower() for lang in ct.submission.get_fields_status()],},
                               context_instance=RequestContext(request))


@login_required
@check_user_can_edit_trial
def step_7(request, trial_pk):
    ct = request.ct

    if not request.user.is_staff and not user_in_group(request.user, 'reviewers'):
        if request.user != ct.submission.creator:
            return render_to_response('403.html', {'site': Site.objects.get_current(),},
                            context_instance=RequestContext(request))

    PrimaryOutcomesSet = modelformset_factory( Outcome,
                                formset=MultilingualBaseFormSet,
                                form=PrimaryOutcomesForm,extra=EXTRA_FORMS,
                                can_delete=True,
                                extra_formset_attrs={
                                    'default_second_language':ct.submission.get_secondary_language(),
                                    'available_languages':[lang.lower() for lang in ct.submission.get_fields_status()],
                                    'display_language':request.trials_language
                                    },
                                )
    SecondaryOutcomesSet = modelformset_factory(Outcome,
                                formset=MultilingualBaseFormSet,
                                form=SecondaryOutcomesForm,extra=EXTRA_FORMS,
                                can_delete=True,
                                extra_formset_attrs={
                                    'default_second_language':ct.submission.get_secondary_language(),
                                    'available_languages':[lang.lower() for lang in ct.submission.get_fields_status()],
                                    'display_language':request.user.get_profile().preferred_language,
                                    },
                                )

    primary_qs = Outcome.objects.filter(trial=ct, interest=choices.OUTCOME_INTEREST[0][0])
    secondary_qs = Outcome.objects.filter(trial=ct, interest=choices.OUTCOME_INTEREST[1][0])

    if request.method == 'POST' and request.can_change_trial:
        primary_outcomes_formset = PrimaryOutcomesSet(request.POST, queryset=primary_qs, prefix='primary')
        secondary_outcomes_formset = SecondaryOutcomesSet(request.POST, queryset=secondary_qs, prefix='secondary')

        if primary_outcomes_formset.is_valid() and secondary_outcomes_formset.is_valid():
            outcomes = primary_outcomes_formset.save(commit=False)
            outcomes += secondary_outcomes_formset.save(commit=False)

            for outcome in outcomes:
                outcome.trial = ct

            primary_outcomes_formset.save()
            secondary_outcomes_formset.save()

            # Executes validation of current trial submission (for mandatory fields)
            trial_validator.validate(ct)

            return HttpResponseRedirect(reverse('step_7',args=[trial_pk]))
    else:
        primary_outcomes_formset = PrimaryOutcomesSet(queryset=primary_qs, prefix='primary')
        secondary_outcomes_formset = SecondaryOutcomesSet(queryset=secondary_qs, prefix='secondary')

    formsets = [primary_outcomes_formset,secondary_outcomes_formset]
    return render_to_response('repository/trial_form.html',
                              {'formsets':formsets,
                               'trial_pk':trial_pk,
                               'title':TRIAL_FORMS[6],
                               'steps': step_list(trial_pk),
                               'remarks':Remark.status_open.filter(submission=ct.submission,context=slugify(TRIAL_FORMS[6])),
                               'default_second_language': ct.submission.get_secondary_language(),
                               'available_languages': [lang.lower() for lang in ct.submission.get_fields_status()],},
                               context_instance=RequestContext(request))


@login_required
@check_user_can_edit_trial
def step_8(request, trial_pk):
    ct = request.ct

    if not request.user.is_staff and not user_in_group(request.user, 'reviewers'):
        if request.user != ct.submission.creator:
            return render_to_response('403.html', {'site': Site.objects.get_current(),},
                            context_instance=RequestContext(request))

    contact_type = {
        'PublicContact': (PublicContact,make_public_contact_form(request.user)),
        'ScientificContact': (ScientificContact,make_scientifc_contact_form(request.user)),
        'SiteContact': (SiteContact,make_site_contact_form(request.user))
    }

    InlineFormSetClasses = []
    for model,form in contact_type.values():
        InlineFormSetClasses.append(
            inlineformset_factory(ClinicalTrial,model,form=form,can_delete=True,extra=EXTRA_FORMS)
        )

    ContactFormSet = modelformset_factory(Contact,
                                          form=make_contact_form(request.user,formset_prefix='new_contact'),
                                          extra=1)

    contact_qs = Contact.objects.none()

    if request.method == 'POST' and request.can_change_trial:
        inlineformsets = [fs(request.POST,instance=ct) for fs in InlineFormSetClasses]
        new_contact_formset = ContactFormSet(request.POST,queryset=contact_qs,prefix='new_contact')

        if not False in [fs.is_valid() for fs in inlineformsets] \
                and new_contact_formset.is_valid():

            for contactform in new_contact_formset.forms:
                if contactform.cleaned_data:
                    Relation = contact_type[contactform.cleaned_data.pop('relation')][0]
                    new_contact = contactform.save(commit=False)
                    new_contact.creator = request.user
                    new_contact.save()
                    Relation.objects.create(trial=ct,contact=new_contact)

            for fs in inlineformsets:
                fs.save()

            # Executes validation of current trial submission (for mandatory fields)
            trial_validator.validate(ct)

            return HttpResponseRedirect(reverse('step_8',args=[trial_pk]))
    else:
        inlineformsets = [fs(instance=ct) for fs in InlineFormSetClasses]
        new_contact_formset = ContactFormSet(queryset=contact_qs,prefix='new_contact')

    formsets = inlineformsets + [new_contact_formset]
    return render_to_response('repository/step_8.html',
                              {'formsets':formsets,
                               'trial_pk':trial_pk,
                               'title':TRIAL_FORMS[7],
                               'steps': step_list(trial_pk),
                               'remarks':Remark.status_open.filter(submission=ct.submission,context=slugify(TRIAL_FORMS[7])),
                               'default_second_language': ct.submission.get_secondary_language(),
                               'available_languages': [lang.lower() for lang in ct.submission.get_fields_status()],},
                               context_instance=RequestContext(request))

@login_required
@check_user_can_edit_trial
def step_9(request, trial_pk):
    # TODO: this function should be on another place
    ct = request.ct

    if not request.user.is_staff and not user_in_group(request.user, 'reviewers'):
        if request.user != ct.submission.creator:
            return render_to_response('403.html', {'site': Site.objects.get_current(),},
                            context_instance=RequestContext(request))

    su = Submission.objects.get(trial=ct)

    NewAttachmentFormSet = modelformset_factory(Attachment,
                                             extra=1,
                                             can_delete=False,
                                             form=NewAttachmentForm)

    existing_attachments = Attachment.objects.filter(submission=su)

    if request.method == 'POST' and request.can_change_trial:

        if 'remove' in request.POST:
            attach = Attachment.objects.get(id=request.POST.get('remove'))
            attach.delete()

            return HttpResponseRedirect(reverse('step_9',args=[trial_pk]))

        else:
            new_attachment_formset = NewAttachmentFormSet(request.POST,
                                                          request.FILES,
                                                          prefix='new')

            if new_attachment_formset.is_valid():
                new_attachments = new_attachment_formset.save(commit=False)

                for attachment in new_attachments:
                    attachment.submission = su

                new_attachment_formset.save()
                return HttpResponseRedirect(reverse('step_9',args=[trial_pk]))

    else:
        new_attachment_formset = NewAttachmentFormSet(queryset=Attachment.objects.none(),
                                                      prefix='new')

    formsets = [new_attachment_formset]

    return render_to_response('repository/attachments.html',
                              {'formsets':formsets,
                               'existing_attachments':existing_attachments,
                               'trial_pk':trial_pk,
                               'title':TRIAL_FORMS[8],
                               'host': request.get_host(),
                               'steps': step_list(trial_pk),
                               'remarks':Remark.status_open.filter(submission=ct.submission,context=slugify(TRIAL_FORMS[8])),
                               'default_second_language': ct.submission.get_secondary_language(),
                               'available_languages': [lang.lower() for lang in ct.submission.get_fields_status()],},
                               context_instance=RequestContext(request))

from repository.xml.generate import xml_ictrp, xml_opentrials, TrialDicList

def trial_ictrp(request, trial_fossil_id, trial_version=None):
    """
    Returns a XML content structured on ICTRP standard, you can find more details
    about it on:

    - http://reddes.bvsalud.org/projects/clinical-trials/wiki/RegistrationDataModel
    - http://reddes.bvsalud.org/projects/clinical-trials/attachment/wiki/RegistrationDataModel/who_ictrp_dtd.txt
    - http://reddes.bvsalud.org/projects/clinical-trials/attachment/wiki/RegistrationDataModel/ICTRP%20Data%20format%201.1%20.doc
    - http://reddes.bvsalud.org/projects/clinical-trials/attachment/wiki/RegistrationDataModel/xmlsample.xml
    - http://reddes.bvsalud.org/projects/clinical-trials/attachment/wiki/RegistrationDataModel/ICTRPTrials.xml
    """

    try:
        fossil = Fossil.objects.get(pk=trial_fossil_id)
    except Fossil.DoesNotExist:
        try:
            qs = Fossil.objects.indexed(trial_id=trial_fossil_id)
            if trial_version:
                fossil = qs.get(revision_sequential=trial_version)
            else:
                fossil = qs.get(is_most_recent=True)
        except Fossil.DoesNotExist:
            raise Http404

    ct = fossil.get_object_fossil()
    xml = xml_ictrp([fossil])

    resp = HttpResponse(xml,
            mimetype = 'text/xml'
            )

    resp['Content-Disposition'] = 'attachment; filename=%s-ictrp.xml' % ct.trial_id

    return resp

def all_trials_ictrp(request):

    trials = ClinicalTrial.fossils.published()
    xml = xml_ictrp(trials)

    resp = HttpResponse(xml,
            mimetype = 'text/xml'
            )

    resp['Content-Disposition'] = 'attachment; filename=%s-ictrp.xml' % settings.TRIAL_ID_PREFIX
    
    log_actions(request.user,'Exported ICTRP XML file')

    return resp

def all_trials_xls(request):
    all_trials = TrialDicList(ClinicalTrial.objects.all())
    
    today = datetime.datetime.now().strftime('%Y-%m-%dT%H_%M')

    filename = "CustomCSV_OT_%s" % today

    output = cStringIO.StringIO()

    import xlwt

    wbk = xlwt.Workbook()
    sheet = wbk.add_sheet('Ensaios')
    sheet_style = xlwt.XFStyle()
    sheet_style.num_format_str = 'YYYY-MM-DD HH:MM:SS'

    header_font = xlwt.Font()
    header_font.bold = True

    header_style = xlwt.XFStyle()
    header_style.font = header_font

    def escrevexls (sheet_par, linha_par, value_list, cell_style):
        col_num = 0 
        for value in value_list:
            sheet_par.write(linha_par,col_num,value, cell_style)
            col_num += 1

    linha = 0

    header_list = ["TIPO_DE_ESTUDO","TITULO_CIENTIFICO_PT","TITULO_CIENTIFICO_EN","TITULO_CIENTIFICO_ES","UTN","TITULO_PUBLICO_PT","TITULO_PUBLICO_EN","TITULO_PUBLICO_ES","ACRONIMO_CIENTIFICO_PT","ACRONIMO_CIENTIFICO_EN","ACRONIMO_CIENTIFICO_ES","ID_SECUNDARIOS_1","ID_SECUNDARIOS_2","ID_SECUNDARIOS_3","PATROCINADOR_PRIMARIO","PATROCINADOR_SECUNDARIO_1","PATROCINADOR_SECUNDARIO_2","APOIO_FINANCEIRO_OU_MATERIAL_1","APOIO_FINANCEIRO_OU_MATERIAL_2","CONDICOES_DE_SAUDE_PT","CONDICOES_DE_SAUDE_EN","CONDICOES_DE_SAUDE_ES","DESCRITORES_GERAIS_1_PT","DESCRITORES_GERAIS_1_EN","DESCRITORES_GERAIS_1_ES","DESCRITORES_GERAIS_2_PT","DESCRITORES_GERAIS_2_EN","DESCRITORES_GERAIS_2_ES","DESCRITORES_ESPECIFICOS_1_PT","DESCRITORES_ESPECIFICOS_1_EN","DESCRITORES_ESPECIFICOS_1_ES","DESCRITORES_ESPECIFICOS_2_PT","DESCRITORES_ESPECIFICOS_2_EN","DESCRITORES_ESPECIFICOS_2_ES","CATEGORIA_DAS_INTERVENCOES_1_PT","CATEGORIA_DAS_INTERVENCOES_1_EN","CATEGORIA_DAS_INTERVENCOES_1_ES","CATEGORIA_DAS_INTERVENCOES_2_PT","CATEGORIA_DAS_INTERVENCOES_2_EN","CATEGORIA_DAS_INTERVENCOES_2_ES","INTERVENCOES_PT","INTERVENCOES_EN","INTERVENCOES_ES","DESCRITORES_INTERVENCAO_1_PT","DESCRITORES_INTERVENCAO_1_EN","DESCRITORES_INTERVENCAO_1_ES","DESCRITORES_INTERVENCAO_2_PT","DESCRITORES_INTERVENCAO_2_EN","DESCRITORES_INTERVENCAO_2_ES","DESCRITORES_INTERVENCAO_3_PT","DESCRITORES_INTERVENCAO_3_EN","DESCRITORES_INTERVENCAO_3_ES","SITUACAO_DO_RECRUTAMENTO","PAIS_DE_RECRUTAMENTO_1","PAIS_DE_RECRUTAMENTO_2","PAIS_DE_RECRUTAMENTO_3","PAIS_DE_RECRUTAMENTO_4","DATA_PRIMEIRO_RECRUTAMENTO","DATA_ULTIMO_RECRUTAMENTO","TAMANHO_DA_AMOSTRA_ALVO","GENERO","IDADE_MIN","UNIDADE_IDADE_MIN","IDADE_MAX","UNIDADE_IDADE_MAX","CRITERIOS_DE_INCLUSAO_PT","CRITERIOS_DE_INCLUSAO_EN","CRITERIOS_DE_INCLUSAO_ES","DESENHO_DO_ESTUDO_PT","DESENHO_DO_ESTUDO_EN","DESENHO_DO_ESTUDO_ES","PROGRAMA_DE_ACESSO","ENFOQUE_DO_ESTUDO","DESENHO_DA_INTERVENCAO","BRACOS","MASCARAMENTO","ALOCACAO","FASE","DESENHO_ESTUDO_OBSERVACIONAL","TEMPORALIDADE","DESFECHO_PRIMARIO_1_PT","DESFECHO_PRIMARIO_1_EN","DESFECHO_PRIMARIO_1_ES","DESFECHO_PRIMARIO_2_PT","DESFECHO_PRIMARIO_2_EN","DESFECHO_PRIMARIO_2_ES","DESFECHO_SECUNDARIO_1_PT","DESFECHO_SECUNDARIO_1_EN","DESFECHO_SECUNDARIO_1_ES","DESFECHO_SECUNDARIO_2_PT","DESFECHO_SECUNDARIO_2_EN","DESFECHO_SECUNDARIO_2_ES","LOGIN","EMAIL","STATUS"]

    escrevexls(sheet, linha, header_list, header_style)
    
    for trial_dic in all_trials:
        linha += 1

        insert_values = []
        for header_elements in header_list:
            elemento = unicode(trial_dic[header_elements])
            insert_values.append(elemento)
        
        try:
            escrevexls(sheet,linha,insert_values,sheet_style)
        except:
            print "---------- %s " % insert_values[30]

    wbk.save(output)

    response = HttpResponse(mimetype='application/zip')
    response['Content-Disposition'] = 'attachment; filename=%s.zip' % filename

    zipped_file = ZipFile(response, 'w', ZIP_DEFLATED)

    csv_name = '%s.xls' % filename
    zipped_file.writestr(csv_name, output.getvalue())

    return response

def trial_otxml(request, trial_id, trial_version=None):
    """
    Returns a XML content structured on OpenTrials standard, you can find more details
    about it on:

    - ToDo
    """

    try:
        fossil = Fossil.objects.get(pk=trial_id)
    except Fossil.DoesNotExist:
        try:
            qs = Fossil.objects.indexed(trial_id=trial_id)
            if trial_version:
                fossil = qs.get(revision_sequential=trial_version)
            else:
                fossil = qs.get(is_most_recent=True)
        except Fossil.DoesNotExist:
            raise Http404

    ct = fossil.get_object_fossil()
    ct.hash_code = fossil.pk
    ct.previous_revision = fossil.previous_revision
    ct.version = fossil.revision_sequential
    ct.status = fossil.indexers.key('status', fail_silent=True).value

    xml = xml_opentrials([ct])

    resp = HttpResponse(xml,
            mimetype = 'text/xml'
            )

    resp['Content-Disposition'] = 'attachment; filename=%s-ot.xml' % ct.trial_id

    return resp

def multi_otxml(request):
    trial_id_list = request.GET.getlist('trial_id')
    if not trial_id_list:
        return HttpResponse(status=205)

    ct_list = []

    for trial_id in trial_id_list:
        try:
            fossil = Fossil.objects.get(pk=trial_id)
        except Fossil.DoesNotExist:
            try:
                qs = Fossil.objects.indexed(trial_id=trial_id)
                fossil = qs.get(is_most_recent=True)
            except Fossil.DoesNotExist:
                raise Http404

        ct = fossil.get_object_fossil()
        ct.hash_code = fossil.pk
        ct.previous_revision = fossil.previous_revision
        ct.version = fossil.revision_sequential
        ct.status = fossil.indexers.key('status', fail_silent=True).value

        ct_list.append(ct)

    xml = xml_opentrials(ct_list)

    resp = HttpResponse(xml,
            mimetype = 'text/xml'
            )

    today = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M')
    resp['Content-Disposition'] = 'attachment; filename=%s-ot.xml' % today

    return resp

def custom_otcsv(request):
    allsubmissions = Submission.objects.all()
    allsubmissions_list = allsubmissions.values('pk','trial_id','created','updated','creator','title','status')

    today = datetime.datetime.now().strftime('%Y-%m-%dT%H_%M')

    filename = "CustomCSV_OT_%s" % today

    output = cStringIO.StringIO() ## temp output csv file

    import xlwt

    wbk = xlwt.Workbook()
    sheet = wbk.add_sheet('Ensaios')
    sheet_style = xlwt.XFStyle()
    sheet_style.num_format_str = 'YYYY-MM-DD HH:MM:SS'

    sheet.col(0).width = 3000
    sheet.col(1).width = 5500
    sheet.col(2).width = 5500
    sheet.col(3).width = 3000
    sheet.col(4).width = 4500
    sheet.col(5).width = 20000

    def escrevexls (sheet_par, linha_par, value_list):
        col_num = 0 
        for value in value_list:
            sheet_par.write(linha_par,col_num,value, sheet_style)
            col_num += 1

    linha = 0

    escrevexls(sheet, linha, ['REQ','Criacao','Atualizado','Status','Usuario','Titulo'])

    for submission in allsubmissions_list:
        linha += 1

        title = submission['title']
        login_creator = str(User.objects.get(pk=submission['creator']))

        try:
            trial_id = ClinicalTrial.objects.get(pk=submission['trial_id'])
            trial_id = unicode(trial_id).split(' ')[0]
        except:
            trial_id = "no_id"

        insert_values = [trial_id,submission['created'],submission['updated'],submission['status'],login_creator,title]

        escrevexls(sheet,linha,insert_values)

    wbk.save(output)

    response = HttpResponse(mimetype='application/zip')
    response['Content-Disposition'] = 'attachment; filename=%s.zip' % filename

    zipped_file = ZipFile(response, 'w', ZIP_DEFLATED)

    csv_name = '%s.xls' % filename
    zipped_file.writestr(csv_name, output.getvalue())

    return response

def advanced_search(request):
    q = request.GET.get('q', '').strip()
    rec_status = request.GET.getlist('rec_status')
    rec_country = request.GET.get('rec_country', '').strip()
    is_observational = request.GET.getlist('is_observ')
    i_type = request.GET.getlist('i_type')
    gender = request.GET.get('gender', '').strip()
    minimum_age = request.GET.get('age_min','').strip()
    maximum_age = request.GET.get('age_max','').strip()
    minimum_age_unit = request.GET.get('age_min_unit','').strip()
    maximum_age_unit = request.GET.get('age_max_unit','').strip()

    recruitment_country_list = localized_vocabulary(CountryCode, request.LANGUAGE_CODE.lower())
    recruitment_status_list = localized_vocabulary(RecruitmentStatus, request.LANGUAGE_CODE.lower())
    institution_type_list = localized_vocabulary(InstitutionType, request.LANGUAGE_CODE.lower())

    return render_to_response('repository/advanced_search.html',
                              {'rec_countries':recruitment_country_list,
                               'rec_status':recruitment_status_list,
                               'i_type':institution_type_list,
                               'q':q,
                               'age_min': minimum_age,
                               'age_max': maximum_age,
                               'search_filters':{'rec_status':rec_status,
                                                 'rec_country':rec_country,
                                                 'is_observ':is_observational,
                                                 'i_type': i_type,
                                                 'gender':gender,
                                                 'minimum_age':minimum_age,
                                                 'maximum_age':maximum_age,
                                                 'minimum_age_unit':minimum_age_unit,
                                                 'maximum_age_unit':maximum_age_unit,                                               },
                              },
                              context_instance=RequestContext(request))


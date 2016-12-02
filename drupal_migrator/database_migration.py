import csv
import io
import json
import os

from datetime import datetime
from django.contrib.auth.models import User
from django.utils import translation
from home.models import Author, Event, Job, Model, ModelVersion, ModelKeywords, Keyword, Profile, License, Platform
from typing import Dict, List

from .json_field_util import get_field_first, get_field

def load_data(model, s: str) -> Dict[int, Dict]:
    f = io.StringIO(s.strip())
    rows = csv.DictReader(f)

    instances = []
    for row in rows:
        instances.append(model(**row))

    model.objects.bulk_create(instances)
    # TODO: set sequence number to start after last value when moved over to Postgres


LICENSE_LEVELS = """id,name,address
    1,"GNU GPL, Version 2",http://www.gnu.org/licenses/gpl-2.0.html
    2,"GNU GPL, Version 3",http://www.gnu.org/licenses/gpl-3.0.html
    3,"Apache License, Version 2.0",http://www.apache.org/licenses/LICENSE-2.0.html
    4,"Creative Commons (cc by)",http://creativecommons.org/licenses/by/3.0/
    5,"Creative Commons (cc by-sa)",http://creativecommons.org/licenses/by-sa/3.0/
    6,"Creative Commons (cc by-nd)",http://creativecommons.org/licenses/by-nd/3.0
    7,"Creative Commons (cc by-nc)",http://creativecommons.org/licenses/by-nc/3.0
    8,"Creative Commons (cc by-nc-sa)",http://creativecommons.org/licenses/by-nc-sa/3.0
    9,"Creative Commons (cc by-nc-nd)",http://creativecommons.org/licenses/by-nc-nd/3.0
    10,"Academic Free License 3.0",http://www.opensource.org/licenses/afl-3.0.php
    11,"BSD 2-Clause",http://opensource.org/licenses/BSD-2-Clause"""

PLATFORM_LEVELS = """id,name,address
    0,Other,NULL
    1,"Ascape 5",http://ascape.sourceforge.net/
    2,Breve,http://www.spiderland.org/
    3,Cormas,http://cormas.cirad.fr/en/outil/outil.htm
    4,DEVSJAVA,http://www.acims.arizona.edu/SOFTWARE/software.shtml
    5,Ecolab,http://ecolab.sourceforge.net/
    6,Mason,http://www.cs.gmu.edu/~eclab/projects/mason/
    7,MASS,http://mass.aitia.ai/
    8,MobilDyc,http://w3.avignon.inra.fr/mobidyc/index.php/English_summary
    9,NetLogo,http://ccl.northwestern.edu/netlogo/
    10,Repast,http://repast.sourceforge.net/
    11,Sesam,http://www.simsesam.de/
    12,StarLogo,http://education.mit.edu/starlogo/
    13,Swarm,http://www.swarm.org/
    14,AnyLogic,http://www.anylogic.com/
    15,Matlab,http://www.mathworks.com/products/matlab/"""


class Extractor:
    def __init__(self, data):
        self.data = data

    @classmethod
    def from_file(cls, file_name):
        with open(file_name, 'r', encoding='UTF-8') as f:
            data = json.load(f)
            return cls(data)

    @staticmethod
    def to_datetime(unix_timestamp: str):
        return datetime.fromtimestamp(float(unix_timestamp))


class EventExtractor(Extractor):
    def _extract(self, raw_event, user_id_map: Dict[str, int]):
        return Event(
            title=raw_event['title'],
            date_created=self.to_datetime(raw_event['created']),
            date_modified=self.to_datetime(raw_event['changed']),
            content=get_field_first(raw_event, 'body', 'value'),
            early_registration_deadline=get_field_first(raw_event, 'field_earlyregistration', 'value', None),
            submission_deadline=get_field_first(raw_event, 'field_submissiondeadline', 'value', None),
            creator_id=user_id_map[raw_event['uid']])

    def extract_all(self, user_id_map: Dict[str, int]):
        events = [self._extract(raw_event, user_id_map) for raw_event in self.data]
        Event.objects.bulk_create(events)


class JobExtractor(Extractor):
    def _extract(self, raw_job: Dict, user_id_map: Dict[str, int]):
        return Job(
            title=raw_job['title'],
            date_created=self.to_datetime(raw_job['created']),
            date_modified=self.to_datetime(raw_job['changed']),
            content=raw_job['body']['und'][0]['value'],
            creator_id=user_id_map[raw_job['uid']])

    def extract_all(self, user_id_map: Dict[str, int]):
        raw_jobs = [raw_job for raw_job in self.data if raw_job['forum_tid'] == "13"]
        jobs = [self._extract(raw_job, user_id_map) for raw_job in raw_jobs]
        Job.objects.bulk_create(jobs)


class UserExtractor(Extractor):
    def _uid(self, raw_user):
        return raw_user['uid']

    def _extract(self, raw_user):
        # print(raw_user)
        return User(
            username=raw_user['name'],
            email=raw_user['mail'])

    def extract_all(self):
        users = [self._extract(raw_user) for raw_user in self.data]
        uids = [self._uid(raw_user) for raw_user in self.data]
        User.objects.bulk_create(users)
        user_id_map = dict(zip(uids, [u[0] for u in User.objects.order_by('id').values_list('id')]))
        return user_id_map


class ProfileExtractor(Extractor):
    def _extract(self, raw_profile, user_id_map):
        return Profile(
            user_id=user_id_map[raw_profile['uid']],
            summary=get_field_first(raw_profile, 'field_profile2_research', 'value'),
            degrees='',  # TODO: change this to a text array field after moving to Postgres

            academia_edu=get_field_first(raw_profile, 'field_profile2_academiaedu_link', 'url'),
            blog=get_field_first(raw_profile, 'field_profile2_blog_link', 'url'),
            curriculum_vitae=get_field_first(raw_profile, 'field_profile2_cv_link', 'url'),
            institution=get_field_first(raw_profile, 'field_profile2_institution_link', 'url'),
            linkedin=get_field_first(raw_profile, 'field_profile2_linkedin_link', 'url'),
            personal=get_field_first(raw_profile, 'field_profile2_personal_link', 'url'),
            research_gate=get_field_first(raw_profile, 'field_profile2_researchgate_link', 'url'))

    def extract_all(self, user_id_map):
        detached_profiles = [self._extract(raw_profile, user_id_map) for raw_profile in self.data]
        Profile.objects.bulk_create(detached_profiles)


class TaxonomyExtractor(Extractor):
    def extract_all(self):
        raw_tags = [raw_tag for raw_tag in self.data if raw_tag['vocabulary_machine_name'] == 'vocabulary_6']
        tag_id_map = {}

        translation.activate('en')
        for raw_tag in raw_tags:
            keyword = Keyword.objects.create(name=raw_tag['name'])
            tag_id_map[raw_tag['tid']] = keyword.id

        return tag_id_map


class AuthorExtractor(Extractor):
    def _extract(self, raw_author):
        return Author(first_name=get_field_first(raw_author, 'field_model_authorfirst', 'value', ''),
                      middle_name=get_field_first(raw_author, 'field_model_authormiddle', 'value', ''),
                      last_name=get_field_first(raw_author, 'field_model_authorlast', 'value', ''))

    def extract_all(self):
        detached_authors = [self._extract(raw_author) for raw_author in self.data]
        item_ids = [raw_author['item_id'] for raw_author in self.data]
        Author.objects.bulk_create(detached_authors)
        author_id_map = dict(zip(item_ids, [a[0] for a in Author.objects.order_by('id').values_list('id')]))
        return author_id_map


class ModelExtractor(Extractor):
    @staticmethod
    def convert_bool_str(str):
        if str in ['0', '1']:
            return str == '1'
        else:
            raise ValueError('replication value "{}" is not valid'.format(str))

    def _extract(self, raw_model, user_id_map, author_id_map):
        content = raw_model['body']['und'][0]['value'] or ''

        raw_author_ids = [raw_author['value'] for raw_author in get_field(raw_model, 'field_model_author')]
        author_ids = [author_id_map[raw_author_id] for raw_author_id in raw_author_ids]
        return (Model(title=raw_model['title'],
                      content=content,
                      date_created=self.to_datetime(raw_model['created']),
                      date_modified=self.to_datetime(raw_model['changed']),
                      is_replicated=self.convert_bool_str(
                          get_field_first(raw_model, 'field_model_replicated', 'value', '0')),
                      reference=get_field_first(raw_model, 'field_model_reference', 'value', ''),
                      replication_reference=get_field_first(raw_model, 'field_model_publication_text', 'value', ''),
                      creator_id=user_id_map[raw_model['uid']]), author_ids)

    def extract_all(self, user_id_map, tag_id_map, author_id_map):
        raw_models = [raw_model for raw_model in self.data if raw_model['body']['und'][0]['value']]
        detached_model_author_ids = [self._extract(raw_model, user_id_map, author_id_map) for raw_model in raw_models]
        nids = [raw_model['nid'] for raw_model in raw_models]

        for (detached_model, author_ids) in detached_model_author_ids:
            detached_model.save()
            for author_id in author_ids:
                detached_model.authors.add(Author.objects.get(id=author_id))

        models = [el[0] for el in detached_model_author_ids]
        model_id_map = dict(zip(nids, [m.id for m in models]))

        model_keywords = []
        for raw_model in raw_models:
            if raw_model['taxonomy_vocabulary_6']:
                for keyword in raw_model['taxonomy_vocabulary_6']['und']:
                    model_keyword = ModelKeywords(model_id=model_id_map[raw_model['nid']],
                                                  keyword_id=tag_id_map[keyword['tid']])
                    model_keywords.append(model_keyword)
        ModelKeywords.objects.bulk_create(model_keywords)

        return model_id_map


class ModelVersionExtractor(Extractor):
    OS_LEVELS = [
        'Other',
        'Linux',
        'Apple OS X',
        'Microsoft Windows',
        'Platform Independent',
    ]

    LANGUAGE_LEVELS = [
        'Other',
        'C',
        'C++',
        'Java',
        'Logo (variant)',
        'Perl',
        'Python',
    ]

    def _load(self, raw_model_version, model_id_map: Dict[str, int]):
        model_nid = get_field_first(raw_model_version, 'field_modelversion_model', 'nid')
        content = get_field_first(raw_model_version, 'body', 'value')

        language = self.LANGUAGE_LEVELS[
            int(get_field_first(raw_model_version, 'field_modelversion_language', 'value', 0))]
        license_id = get_field_first(raw_model_version, 'field_modelversion_license', 'value', None)
        os = self.OS_LEVELS[int(get_field_first(raw_model_version, 'field_modelversion_os', 'value', 0))]
        platform_id = int(get_field_first(raw_model_version, 'field_modelversion_platform', 'value', 0))

        if model_nid and model_nid in model_id_map:
            model_version = ModelVersion(
                content=content,
                date_created=self.to_datetime(raw_model_version['created']),
                date_modified=self.to_datetime(raw_model_version['changed']),

                language=language,
                license_id=license_id,
                os=os,
                platform_id=platform_id,

                model_id=model_id_map[model_nid])
            model_version.save()
            return raw_model_version['nid'], model_version.id

    def extract_all(self, model_id_map: Dict[str, int]):
        model_version_id_map = {}
        for raw_model_version in self.data:
            result = self._load(raw_model_version, model_id_map)
            if result:
                drupal_id, pk = result
                model_version_id_map[drupal_id] = pk
        return model_version_id_map


class IDMapper:
    def __init__(self, author_id_map, user_id_map, tag_id_map, model_id_map, model_version_id_map):
        self._maps = {
            Author: author_id_map,
            User: user_id_map,
            ModelKeywords: tag_id_map,
            Model: model_id_map,
            ModelVersion: model_version_id_map
        }

    def __getitem__(self, item):
        return self._maps[item]


def load(directory: str):
    # TODO: associate picture with profile
    author_extractor = AuthorExtractor.from_file(os.path.join(directory, "Author.json"))
    event_extractor = EventExtractor.from_file(os.path.join(directory, "Event.json"))
    job_extractor = JobExtractor.from_file(os.path.join(directory, "Forum.json"))
    model_extractor = ModelExtractor.from_file(os.path.join(directory, "Model.json"))
    model_version_extractor = ModelVersionExtractor.from_file(os.path.join(directory, "ModelVersion.json"))
    profile_extractor = ProfileExtractor.from_file(os.path.join(directory, "Profile2.json"))
    taxonomy_extractor = TaxonomyExtractor.from_file(os.path.join(directory, "Taxonomy.json"))
    user_extractor = UserExtractor.from_file(os.path.join(directory, "User.json"))

    load_data(License, LICENSE_LEVELS)
    load_data(Platform, PLATFORM_LEVELS)

    author_id_map = author_extractor.extract_all()
    user_id_map = user_extractor.extract_all()
    job_extractor.extract_all(user_id_map)
    event_extractor.extract_all(user_id_map)
    tag_id_map = taxonomy_extractor.extract_all()
    model_id_map = model_extractor.extract_all(user_id_map=user_id_map, tag_id_map=tag_id_map,
                                               author_id_map=author_id_map)
    model_version_id_map = model_version_extractor.extract_all(model_id_map)
    profile_extractor.extract_all(user_id_map)

    return IDMapper(author_id_map, user_id_map, tag_id_map, model_id_map, model_version_id_map)

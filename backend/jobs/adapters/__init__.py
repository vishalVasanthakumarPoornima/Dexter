from backend.jobs.adapters.adzuna import AdzunaAdapter
from backend.jobs.adapters.arbeitnow import ArbeitnowAdapter
from backend.jobs.adapters.ashby import AshbyAdapter
from backend.jobs.adapters.brave_search import BraveSearchAdapter
from backend.jobs.adapters.careerjet import CareerjetAdapter
from backend.jobs.adapters.company_careers import CompanyCareersAdapter
from backend.jobs.adapters.github_lists import GitHubListsAdapter
from backend.jobs.adapters.greenhouse import GreenhouseAdapter
from backend.jobs.adapters.jooble import JoobleAdapter
from backend.jobs.adapters.lever import LeverAdapter
from backend.jobs.adapters.manual_link import ManualLinkAdapter
from backend.jobs.adapters.recruitee import RecruiteeAdapter
from backend.jobs.adapters.remotive import RemotiveAdapter
from backend.jobs.adapters.restricted_manual import RestrictedManualAdapter
from backend.jobs.adapters.rss import RSSAdapter
from backend.jobs.adapters.smartrecruiters import SmartRecruitersAdapter
from backend.jobs.adapters.themuse import TheMuseAdapter
from backend.jobs.adapters.usajobs import USAJobsAdapter
from backend.jobs.adapters.web_discovery import WebDiscoveryAdapter


ADAPTER_CLASSES = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "usajobs": USAJobsAdapter,
    "adzuna": AdzunaAdapter,
    "remotive": RemotiveAdapter,
    "ashby": AshbyAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "recruitee": RecruiteeAdapter,
    "themuse": TheMuseAdapter,
    "arbeitnow": ArbeitnowAdapter,
    "careerjet": CareerjetAdapter,
    "jooble": JoobleAdapter,
    "brave_search": BraveSearchAdapter,
    "github_lists": GitHubListsAdapter,
    "rss": RSSAdapter,
    "manual_link": ManualLinkAdapter,
    "company_careers": CompanyCareersAdapter,
    "web_discovery": WebDiscoveryAdapter,
    "restricted_manual": RestrictedManualAdapter,
}

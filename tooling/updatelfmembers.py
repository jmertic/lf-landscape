#!/usr/bin/env python3
#
# Copyright this project and it's contributors
# SPDX-License-Identifier: Apache-2.0
#
# encoding=utf8

# built in modules
import csv
import sys
import re
import os
import os.path
from datetime import datetime

# third party modules
from yaml.representer import SafeRepresenter
import ruamel.yaml
from ruamel import yaml
import requests
import validators
from bs4 import BeautifulSoup
from url_normalize import url_normalize
from tld import get_fld
from tld.utils import update_tld_names
from simple_salesforce import Salesforce
from pycrunchbase import CrunchBase

class Config:

    sf_username = None
    sf_password = None
    sf_token = None

    def __init__(self, config_file):
        if config_file != '' and os.path.isfile(config_file):
            try:
                with open(config_file, 'r') as stream:
                    data_loaded = yaml.safe_load(stream)
            except:
                sys.exit(config_file+" config file is not defined")

            if 'sf_username' in data_loaded:
                self.sf_username = data_loaded['sf_username']
            if 'sf_password' in data_loaded:
                self.sf_password = data_loaded['sf_password']
            if 'sf_token' in data_loaded:
                self.sf_token = data_loaded['sf_token']
            elif 'SFDC_TOKEN' in os.environ:
                self.token = os.environ['SFDC_TOKEN']
            else:
                raise Exception('Salesforce security token is not defined. Set \'token\' in {config_file} or set SFDC_TOKEN environment variable to a valid Salesforce security token'.format(config_file=config_file))

#
# Member object to ensure we have normalization on fields. Only required fields are defined; others can be added dynamically.
#
class Member:

    orgname = None
    membership = None
    __website = None
    __logo = None
    __crunchbase = None

    # we'll use these to keep track of whether the member has valid fields
    _validWebsite = False
    _validLogo = False
    _validCrunchbase = False

    @property
    def crunchbase(self):
        return self.__crunchbase

    @crunchbase.setter
    def crunchbase(self, crunchbase):
        if crunchbase is None:
            raise ValueError("Member.crunchbase must be not be blank for {orgname}".format(orgname=self.orgname))
        if not crunchbase.startswith('https://www.crunchbase.com/organization/'):
            raise ValueError("Member.crunchbase for {orgname} must be set to a valid crunchbase url - '{crunchbase}' provided".format(crunchbase=crunchbase,orgname=self.orgname))

        self._validCrunchbase = True
        self.__crunchbase = crunchbase

    @property
    def website(self):
        return self.__website

    @website.setter
    def website(self, website):
        if website is None:
            raise ValueError("Member.website must be not be blank for {orgname}".format(orgname=self.orgname))

        normalizedwebsite = url_normalize(get_fld(url_normalize(website), fail_silently=True), default_scheme='https')
        if not normalizedwebsite:
            raise ValueError("Member.website for {orgname} must be set to a valid website - '{website}' provided".format(website=website,orgname=self.orgname))

        self._validWebsite = True
        self.__website = normalizedwebsite

    @property
    def logo(self):
        return self.__logo

    @logo.setter
    def logo(self, logo):
        if logo is None:
            raise ValueError("Member.logo must be not be blank for {orgname}".format(orgname=self.orgname))

        if not os.path.splitext(logo)[1] == '.svg':
            raise ValueError("Member.logo for {orgname} must be an svg file - '{logo}' provided".format(logo=logo,orgname=self.orgname))

        self._validLogo = True
        self.__logo = logo

    def toLandscapeItemAttributes(self):
        dict = {}
        dict['item'] = None
        attributes = [a for a in dir(self) if not a.startswith('_') and not callable(getattr(self, a))]
        for i in attributes:
            if i == 'orgname':
                dict['name'] = getattr(self,i)
            elif i == 'website':
                dict['homepage_url'] = getattr(self,i)
            elif i == 'membership':
                continue
            else:
                dict[i] = getattr(self,i)

        return dict

    def isValidLandscapeItem(self):
        return self._validWebsite and self._validLogo and self._validCrunchbase and self.orgname != ''

#
# Abstract Members class to normalize the methods used for the other ways of getting a member's info
#
class Members:

    def loadData(self):
        pass

    def find(self, org):
        pass

    def normalizeCompany(self, company):

        company = company.replace(', Inc.','')
        company = company.replace(', Ltd','')
        company = company.replace(',Ltd','')
        company = company.replace(' Inc.','')
        company = company.replace(' Co.','')
        company = company.replace(' Corp.','')
        company = company.replace(' AB','')
        company = company.replace(' AG','')
        company = company.replace(' Pty Ltd','')
        company = company.replace(' Pte Ltd','')
        company = company.replace(' Ltd','')
        company = company.replace(', LLC','')
        company = company.replace(' LLC','')
        company = company.replace(' LLP','')
        company = company.replace(' SPA','')
        company = company.replace(' GmbH','')
        company = company.replace(' PBC','')
        company = company.replace(' Limited','')
        company = company.replace(' s.r.o.','')
        company = company.replace(' srl','')
        company = company.replace(' s.r.l.','')
        company = company.replace(' a.s.','')
        company = company.replace(' S.A.','')
        company = company.replace('.','')
        company = company.replace(' (member)','')
        company = company.replace(' (supporter)','')
        company = re.sub(r'\(.*\)','',company)

        return company.strip()

    def normalizeURL(self, url):
        return url_normalize(url)

class SFDCMembers(Members):

    members = []
    sf_username = None
    sf_password = None
    sf_token = None

    def __init__(self, sf_username = None, sf_password = None, sf_token = None, loadData = False):
        if ( sf_username and sf_password and sf_token ):
            self.sf_username = sf_username
            self.sf_password = sf_password
            self.sf_token = sf_token
            if loadData:
                self.loadData()

    def loadData(self):
        print("--Loading SFDC Members data--")
        sf = Salesforce(username=self.sf_username,password=self.sf_password,security_token=self.sf_token)
        result = sf.query("select Account.Name, Account.Website, Account.Logo_URL__c, Product2.Name from Asset where Asset.Status in ('Active','Purchased') and Asset.Project__c = 'The Linux Foundation'")

        for record in result['records']:
            try:
                member = Member()
                member.orgname = record['Account']['Name']
                member.website = record['Account']['Website']
                member.membership = record['Product2']['Name']
                member.logo = record['Account']['Logo_URL__c']
                member.crunchbase = ''
            except ValueError as e:
                print(e)

            self.members.append(member)

    def find(self, org, website, membership):
        normalizedorg = self.normalizeCompany(org)
        normalizedwebsite = self.normalizeURL(website)

        for member in self.members:
            if ( self.normalizeCompany(member.org) == normalizedorg or member.website == website) and member.membership == membership:
                return member

        return False

class LandscapeMembers(Members):

    members = []
    landscapeListYAML = 'https://raw.githubusercontent.com/cncf/landscapeapp/master/landscapes.yml'
    landscapeSettingsYAML = 'https://raw.githubusercontent.com/{repo}/master/settings.yml'
    landscapeLandscapeYAML = 'https://raw.githubusercontent.com/{repo}/master/landscape.yml'
    landscapeLogo = 'https://raw.githubusercontent.com/{repo}/master/hosted_logos/{logo}'

    def __init__(self, landscapeListYAML = None, loadData = False):
        if landscapeListYAML:
            self.landscapeListYAML = landscapeListYAML
        if loadData:
            self.loadData()

    def loadData(self):
        print("--Loading other landscape members data--")

        response = requests.get(self.landscapeListYAML)
        landscapeList = yaml.load(response.content, Loader=ruamel.yaml.RoundTripLoader)

        for landscape in landscapeList['landscapes']:
            print("Loading "+landscape['name']+"...")

            # first figure out where memberships live
            response = requests.get(self.landscapeSettingsYAML.format(repo=landscape['repo']))
            settingsYaml = yaml.load(response.content, Loader=ruamel.yaml.RoundTripLoader)
            membershipKey = settingsYaml['global']['membership']

            # then load in members only
            response = requests.get(self.landscapeLandscapeYAML.format(repo=landscape['repo']))
            landscapeYaml = yaml.load(response.content, Loader=ruamel.yaml.RoundTripLoader)
            for category in landscapeYaml['landscape']:
                if membershipKey in category['name']:
                    for subcategory in category['subcategories']:
                        for item in subcategory['items']:
                            if not item.get('crunchbase'):
                                item['crunchbase'] = ''
                            try:
                                member = Member()
                                member.membership = ''
                                member.orgname = item['name']
                                member.website = item['homepage_url']
                                member.logo = self.normalizeLogo(item['logo'],landscape['repo'])
                                member.crunchbase = item['crunchbase']
                                for key, value in item.items():
                                    setattr(member, key, value)
                            except ValueError as e:
                                print(e)

                            self.members.append(member)

    def find(self, org, website):
        normalizedorg = self.normalizeCompany(org)
        normalizedwebsite = self.normalizeURL(website)

        for member in self.members:
            if ( self.normalizeCompany(member.orgname) == normalizedorg or member.website == website):
                return member

        return False

    def normalizeLogo(self, logo, landscapeRepo):
        if logo is None:
            return ""

        if 'https://' in logo or 'http://' in logo:
            return logo

        return self.landscapeLogo.format(repo=landscapeRepo,logo=logo)

class CrunchbaseMembers(Members):

    members = []
    crunchbaseKey = ''

    def __init__(self, crunchbaseKey = None, loadData = False):
        if crunchbaseKey:
            self.crunchbaseKey = crunchbaseKey
        elif 'CRUNCHBASE_KEY' in os.environ:
            self.crunchbaseKey = os.getenv('CRUNCHBASE_KEY')

    def loadData(self):
        # load from bulk export file contents


        # we lazy load in data since it's kinda wierd to load all of Crunchbase ;-)
        return

    def find(self, org, website):

        return False

        normalizedorg = self.normalizeCompany(org)
        normalizedwebsite = self.normalizeURL(website)

        cb = CrunchBase(self.crunchbaseKey)

        for result in cb.organizations(org):
            company = cb.organization(result.permalink)
            if self.normalizeCompany(company.name) == normalizedorg:
                try:
                    member = Member()
                    member.membership = ''
                    member.orgname = company.name
                    member.website = self.normalizeURL(company.homepage_url)
                    member.logo = '' # crunchbase doesn't support SVGs, so they are useless to us
                    member.crunchbase = "https://www.crunchbase.com/organization/{org}".format(org=result.permalink)
                except ValueError as e:
                    print(e)

                return member

        return False

class LFWebsiteMembers(Members):

    members = []
    lfwebsiteurl = 'https://www.linuxfoundation.org/membership/members/'

    def __init__(self, loadData = False):
        if loadData:
            self.loadData()

    def loadData(self):
        print("--Loading members listed on LF Website--")

        response = requests.get(self.lfwebsiteurl)
        soup = BeautifulSoup(response.content, "html.parser")
        companies = soup.find_all("div", class_="single-member-icon")
        for entry in companies:
            try:
                member = Member()
                member.membership = ''
                member.orgname = entry.contents[1].contents[0].attrs['alt']
                member.website = self.normalizeURL(entry.contents[1].attrs['href'])
                member.logo = entry.contents[1].contents[0].attrs['src']
                member.crunchbase = ''
            except ValueError as e:
                print(e)

            self.members.append(member)

    def find(self, org, website):
        normalizedorg = self.normalizeCompany(org)
        normalizedwebsite = self.normalizeURL(website)

        for member in self.members:
            if (self.normalizeCompany(member.orgname) == normalizedorg) or (member.website == normalizedwebsite):
                return member

        return False

class LFLandscape:

    landscapefile = '../landscape.yml'
    landscape = None
    landscapeMembers = None
    missingcsvfile = 'missing.csv'
    _missingcsvfilewriter = None

    membersAdded = 0
    membersUpdated = 0

    def __init__(self):
        self.landscape = yaml.load(open(self.landscapefile, 'r', encoding="utf8", errors='ignore'), Loader=ruamel.yaml.RoundTripLoader)
        for x in self.landscape['landscape']:
            if x['name'] == 'LF Member Company':
                self.landscapeMembers = x['subcategories']

    def writeMissing(self, name, logo, homepage_url, crunchbase):
        if self._missingcsvfilewriter is None:
            self._missingcsvfilewriter = csv.writer(open(self.missingcsvfile, mode='w'), delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL)
            self._missingcsvfilewriter.writerow(['name','logo','homepage_url','crunchbase'])

        self._missingcsvfilewriter.writerow([name, logo, homepage_url, crunchbase])

    def hostLogo(self,logo,orgname):
        if 'https://' not in logo and 'http://' not in logo:
            return logo

        filename = str(orgname).strip().replace(' ', '_')
        filename = re.sub(r'(?u)[^-\w.]', '', filename)
        i = 1
        while os.path.isfile("../hosted_logos/"+filename+".svg"):
            filename = filename+"_"+str(i)
            i = i + 1

        r = requests.get(logo, allow_redirects=True)
        open("../hosted_logos/"+filename+".svg", 'wb').write(r.content)

        return filename+".svg"

    def updateLandscape(self):
        # now write it back
        for x in self.landscape['landscape']:
            if x['name'] == 'LF Member Company':
                x['subcategories'] = self.landscapeMembers

        with open(self.landscapefile, 'w', encoding = "utf-8") as landscapefileoutput:
            landscapefileoutput.write( yaml.dump(self.landscape, default_flow_style=False, allow_unicode=True, Dumper=ruamel.yaml.RoundTripDumper) )

        print("Successfully added "+str(self.membersAdded)+" LF members and updated "+str(self.membersUpdated)+" member entries")


def main():

    startTime = datetime.now()

    # load config
    config = Config("config.yaml")

    # load member data sources
    sfdcmembers = SFDCMembers(loadData = True, sf_username = config.sf_username, sf_password = config.sf_password, sf_token = config.sf_token)
    lfwmembers  = LFWebsiteMembers(loadData = True)
    cbmembers   = CrunchbaseMembers(loadData = True)
    lsmembers   = LandscapeMembers(loadData = True)
    lflandscape = LFLandscape()

    # Iterate through the SFDCMembers and update the landscapeMembers
    for member in sfdcmembers.members:
        found = 0
        print("Processing "+member.orgname)
        # overlay crunchbase data to match
        lsmember = lsmembers.find(member.orgname, member.website)
        if lookupmember:
            try:
                print("...Updating crunchbase from landscape")
                member.crunchbase = lsmember.crunchbase
            except ValueError as e:
                print(e)
        else
            cbmember = cbmembers.find(member.orgname,member.website)
            if cbmember:
                try:
                    print("...Updating crunchbase from Crunchbase")
                    member.crunchbase = cbmember.crunchbase
                except ValueError as e:
                    print(e)
        for memberClass in lflandscape.landscapeMembers:
            for landscapeMember in memberClass['items']:
                if sfdcmembers.crunchbase == landscapeMember['crunchbase'] or sfdcmembers.normalizeCompany(landscapeMember['name']) == sfdcmembers.normalizeCompany(member.orgname):
                    print("...Already in landscape")
                    found = 1
                    # Don't touch the entry!!!
                    #
                    # added = 0
                    #
                    # # lookup in other landscapes
                    # lookupmember = lsmembers.find(landscapeMember['name'], landscapeMember['homepage_url'])
                    # if lookupmember:
                    #     for key, value in lookupmember.toLandscapeItemAttributes().items():
                    #         # update from other landscape if
                    #         if ( key not in landscapeMember.keys() or landscapeMember[key] == '' ) and key != 'membership':
                    #             print("...Updating {key} from other landscape".format(key=key))
                    #             landscapeMember[key] = value
                    #     added += 1
                    # # not in other landscape, will need to parse through data
                    # else:
                    #     # lookup on LF lfwebsite
                    #     lookupwebsite = lfwmembers.find(landscapeMember['name'], landscapeMember['homepage_url'])
                    #     if lookupwebsite:
                    #         if ( 'logo' not in landscapeMember or landscapeMember['logo'] == '' ) and '.svg' in lookupwebsite['logo']:
                    #             print("...Updating logo from LF website")
                    #             landscapeMember['logo'] = lookupwebsite.logo
                    #             added += 1
                    #         if 'homepage_url' not in landscapeMember:
                    #             print("...Updating homepage_url from LF website")
                    #             landscapeMember['homepage_url'] = lookupwebsite.website
                    #             added += 1
                    #     # else lookup in LF SFDC data
                    #     if 'logo' not in landscapeMember or landscapeMember['logo'] == '':
                    #         print("...Updating logo from SFDC")
                    #         landscapeMember['logo'] = member.logo
                    #         added += 1
                    #     if 'homepage_url' not in landscapeMember or landscapeMember['homepage_url'] == '':
                    #         print("...Updating homepage_url from SFDC")
                    #         landscapeMember['homepage_url'] = member.website
                    #         added += 1
                    #     if 'crunchbase' not in landscapeMember or landscapeMember['crunchbase'] == '':
                    #         cbmember = cbmembers.find(landscapeMember['name'], landscapeMember['homepage_url'])
                    #         if crunchbase:
                    #             print("...Updating crunchbase from Crunchbase")
                    #             landscapeMember['crunchbase'] = cbmember.crunchbase
                    #             added += 1
                    #     # Write out to missing.csv if it's missing key parameters
                    #     if ( ( not landscapeMember['crunchbase'] or 'https://www.crunchbase.com' not in landscapeMember['crunchbase'] )
                    #         or ( not landscapeMember['logo'] or not landscapeMember['logo'].endswith('.svg') )
                    #         or ( not landscapeMember['homepage_url'] or not validators.url(landscapeMember['homepage_url']) ) ) :
                    #
                    #         lflandscape.writeMissing(
                    #             landscapeMember['name'],
                    #             landscapeMember['logo'],
                    #             landscapeMember['homepage_url'],
                    #             landscapeMember['crunchbase'])
                    #
                    # if added > 0:
                    #     lflandscape.membersUpdated += 1

        if found == 0:
            # if not found, add it
            print("...Not in landscape")
            lflandscape.membersAdded += 1
            for memberClass in lflandscape.landscapeMembers:
                if (( member.membership == "Associate Membership" and memberClass['name'] == 'Associate' )
                    or (member.membership == "Gold Membership" and memberClass['name'] == 'Gold')
                    or (member.membership == "Platinum Membership" and memberClass['name'] == 'Platinum')
                    or (member.membership == "Silver Membership" and memberClass['name'] == 'Silver')
                    or (member.membership == "Silver Membership - MPSF" and memberClass['name'] == 'Silver')
                ):
                    # lookup in other landscapes
                    lookupmember = lsmembers.find(member.orgname, member.website)
                    if lookupmember:
                        print("...Data from other landscape")
                        for key, value in lookupmember.toLandscapeItemAttributes().items():
                            try:
                                setattr(member, key, value)
                            except ValueError as e:
                                print(e)
                    else:
                        print("...Data from SFDC")
                        # overlay lfwebsite data
                        lfwmember = lfwmembers.find(member.orgname,member.website)
                        if lfwmember:
                            if lfwmember.logo is not None and lfwmember.logo != '':
                                print("...Updating logo from LF website")
                                member.logo = lfwmember.logo
                            if lfwmember.website is not None and lfwmember.website != '':
                                print("...Updating website from LF website")
                                member.website = lfwmember.website

                    # Write out to missing.csv if it's missing key parameters
                    if not member.isValidLandscapeItem():
                        print("...Missing key attributes - skip")
                        lflandscape.writeMissing(
                            member.orgname,
                            member.logo,
                            member.website,
                            member.crunchbase
                            )
                    # otherwise we can add it
                    else:
                        print("...Added to Landscape")
                        # host the logo
                        member.logo = lflandscape.hostLogo(logo=member.logo,orgname=member.orgname)
                        memberClass['items'].append(member.toLandscapeItemAttributes())

    lflandscape.updateLandscape()
    print("This took "+str(datetime.now() - startTime)+" seconds")

if __name__ == '__main__':
    main()

#!/usr/bin/env python
#
# Copyright this project and it's contributors
# SPDX-License-Identifier: Apache-2.0
#
# encoding=utf8

from ruamel import yaml
from yaml.representer import SafeRepresenter
from url_normalize import url_normalize
import csv
import sys
import ruamel.yaml
import requests
import validators
import re
from datetime import datetime
from bs4 import BeautifulSoup
from tld import get_fld
from tld.utils import update_tld_names
from simple_salesforce import Salesforce

startTime = datetime.now()
update_tld_names()

class Lookup:

    orglist = {}
    lfwebsitelist = []
    landscapes = {}
    landscapeList = {}

    # lookup entries for members in the other landscapes
    def memberLandscape(company, homepage):

        normalizedCompany = Lookup.normalize(company)
        normalizedHomepage = get_fld(url_normalize(homepage), fail_silently=True)

        if not Lookup.landscapes:
            print("--Building landscape cache--")
            if not Lookup.landscapeList:
                response = requests.get('https://raw.githubusercontent.com/cncf/landscapeapp/master/landscapes.yml')
                Lookup.landscapeList = yaml.load(response.content, Loader=ruamel.yaml.RoundTripLoader)
            for landscape in Lookup.landscapeList['landscapes']:
                print("Loading "+landscape['name']+"...")
                # first figure out where memberships live
                response = requests.get('https://raw.githubusercontent.com/'+landscape['repo']+'/master/settings.yml')
                settingsYaml = yaml.load(response.content, Loader=ruamel.yaml.RoundTripLoader)
                membershipKey = settingsYaml['global']['membership']
                # then load in members only
                response = requests.get('https://raw.githubusercontent.com/'+landscape['repo']+'/master/landscape.yml')
                landscapeYaml = yaml.load(response.content, Loader=ruamel.yaml.RoundTripLoader)
                for category in landscapeYaml['landscape']:
                    if membershipKey in category['name']:
                        Lookup.landscapes[landscape['name']] = category

        print("...Looking up other landscapes")
        # now iterate through all the landscapes
        for landscape in Lookup.landscapes:
            for landscapeMemberItems in Lookup.landscapes[landscape]['subcategories']:
                for landscapeMember in landscapeMemberItems['items']:
                    # first try to match by normalized company name
                    landscapeMember['name'] = landscapeMember['name'].replace(' (member)','')
                    normalizedName = Lookup.normalize(landscapeMember['name'])
                    if normalizedName.lower() in [company.lower(),normalizedCompany.lower()] :
                        print("...Found in "+landscape+" - updating")
                        landscapeMember['logo'] = Lookup.logoURL(landscape,landscapeMember['logo'])
                        return landscapeMember
                    # if that doesn't work, match by URL
                    if landscapeMember['homepage_url'] != '' and normalizedHomepage != '' and get_fld(url_normalize(landscapeMember['homepage_url']), fail_silently=True) == normalizedHomepage:
                        print("...Found in "+landscape+" - updating")
                        if normalizedCompany == "Project Haystack":
                            print(homepage)
                            print(landscapeMember['homepage_url'])
                            print(url_normalize(landscapeMember['homepage_url']))
                            print(get_fld(url_normalize(landscapeMember['homepage_url']), fail_silently=True))
                            print(normalizedHomepage)
                        landscapeMember['logo'] = Lookup.logoURL(landscape,landscapeMember['logo'])
                        return landscapeMember

        return {}

    def memberLFWebsite(company, url):

        company = Lookup.normalize(company)
        if not Lookup.lfwebsitelist:
            print("--Building lfwebsite cache--")
            response = requests.get('https://www.linuxfoundation.org/membership/members/')
            soup = BeautifulSoup(response.content, "html.parser")
            companies = soup.find_all("div", class_="single-member-icon")
            for entry in companies:
                url = entry.contents[1].attrs['href']
                logo = entry.contents[1].contents[0].attrs['src']
                name = Lookup.normalize(entry.contents[1].contents[0].attrs['alt'])
                Lookup.lfwebsitelist.append(dict(name = name, url = url, logo = logo))

        for entry in Lookup.lfwebsitelist:
            if entry['name'].lower() == company.lower():
                return dict(logo = entry['logo'], url = entry['url'])
            if entry['url'] == url:
                return dict(logo = entry['logo'], url = entry['url'])

        return {}

    def memberCrunchbase(company):

        company = Lookup.normalize(company)

        if not Lookup.orglist:
            print("--Building Crunchbase cache--")
            crunchbasefile = 'organizations.csv'
            crunchbaselist = csv.reader(open(crunchbasefile, 'r', encoding="utf8", errors='ignore'))
            for organization in crunchbaselist:
                Lookup.orglist[organization[1]] = Lookup.normalize(organization[0])

        for key, value in Lookup.orglist.items():
            if value.lower() == company.lower():
                return "https://www.crunchbase.com/organization/"+key

        return ''

    def normalize(company):

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
        company = re.sub(r'\(.*\)','',company)

        return company.strip()

    def logoURL(landscapeName, logo):

        if logo is None:
            return ""

        if 'https://' in logo or 'http://' in logo:
            return logo

        if not Lookup.landscapeList:
            response = requests.get('https://raw.githubusercontent.com/cncf/landscapeapp/master/landscapes.yml')
            Lookup.landscapeList = yaml.load(response.content, Loader=ruamel.yaml.RoundTripLoader)

        for landscape in Lookup.landscapeList['landscapes']:
            if landscapeName in landscape['name']:
                return 'https://raw.githubusercontent.com/'+landscape['repo']+'/master/hosted_logos/'+logo

        return ''

# Override the dumper to set nulls correctly
# def my_represent_none(self, data):
#     return self.represent_scalar(u'tag:yaml.org,2002:null', u'null')
# yaml.add_representer(type(None), my_represent_none)

# First open SFDC export file from report
sfdcfile = 'sfdcexport.csv'
memberslist = csv.reader(open(sfdcfile, 'r', encoding="utf8", errors='ignore'))
next(memberslist)  # Skip header

# Second open CSV files for outputing entries with missing logos, website, or homepage_url ( all required )
missingcsvfile = 'missing.csv'
missingcsvwriter = csv.writer(open(missingcsvfile, mode='w'), delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL)
missingcsvwriter.writerow(['name','logo','homepage_url','crunchbase'])

# Now open the landscape file we will write to; navigate to the members section we will be updating
landscapefile = '../landscape.yml'
landscape = yaml.load(open(landscapefile, 'r', encoding="utf8", errors='ignore'), Loader=ruamel.yaml.RoundTripLoader)
for x in landscape['landscape']:
    if x['name'] == 'LF Member Company':
        landscapeMembers = x['subcategories']

# Iterate through the memberslist and update the landscapeMembers
countNew = 0
countUpdates = 0
for member in memberslist:
    found = 0
    print("Processing "+member[0])
    for memberClass in landscapeMembers:
        for landscapeMember in memberClass['items']:
            if landscapeMember['name'] == member[0]:
                # if found, update
                print("...Already in landscape")
                found = 1
                added = 0
                # lookup in other landscapes
                lookupmember = Lookup.memberLandscape(landscapeMember['name'], landscapeMember['homepage_url'])
                if lookupmember:
                    for key, value in lookupmember.items():
                        if key not in landscapeMember.keys() or landscapeMember[key] == '':
                            landscapeMember[key] = value
                    added += 1
                # not in other landscape, will need to parse through data
                else:
                    # lookup on LF lfwebsite
                    lookupwebsite = Lookup.memberLFWebsite(landscapeMember['name'], landscapeMember['homepage_url'])
                    if lookupwebsite:
                        if ( 'logo' not in landscapeMember or landscapeMember['logo'] == '' ) and '.svg' in lookupwebsite['logo']:
                            print("...Updating logo from LF website")
                            landscapeMember['logo'] = lookupwebsite['logo']
                            added += 1
                        if 'homepage_url' not in landscapeMember:
                            print("...Updating homepage_url from LF website")
                            landscapeMember['homepage_url'] = lookupwebsite['url']
                            added += 1
                    # else lookup in LF SFDC data
                    if 'logo' not in landscapeMember or landscapeMember['logo'] == '':
                        print("...Updating logo from SFDC")
                        landscapeMember['logo'] = member[1]
                        added += 1
                    if 'homepage_url' not in landscapeMember or landscapeMember['homepage_url'] == '':
                        print("...Updating homepage_url from SFDC")
                        landscapeMember['homepage_url'] = url_normalize(member[2])
                        added += 1
                    if 'crunchbase' not in landscapeMember or landscapeMember['crunchbase'] == '':
                        crunchbase = Lookup.memberCrunchbase(member[0])
                        if crunchbase:
                            print("...Updating crunchbase")
                            landscapeMember['crunchbase'] = crunchbase
                            added += 1
                    # Write out to missing.csv if it's missing key parameters
                    if ( ( not landscapeMember['crunchbase'] or 'https://www.crunchbase.com' not in landscapeMember['crunchbase'] )
                        or ( not landscapeMember['logo'] or not landscapeMember['logo'].endswith('.svg') )
                        or ( not landscapeMember['homepage_url'] or not validators.url(landscapeMember['homepage_url']) ) ) :
                        missingcsvwriter.writerow([landscapeMember['name'],landscapeMember['logo'],landscapeMember['homepage_url'],landscapeMember['crunchbase']])

                if added > 0:
                    countUpdates += 1

    if found == 0 and not 'test' in member[0] and not 'Test' in member[0]:
        # if not found, add it
        print("...Not in landscape")
        countNew += 1
        for memberClass in landscapeMembers:
            if (( member[3] == "Associate Membership" and memberClass['name'] == 'Associate' )
                or (member[3] == "Gold Membership" and memberClass['name'] == 'Gold')
                or (member[3] == "Platinum Membership" and memberClass['name'] == 'Platinum')
                or (member[3] == "Silver Membership" and memberClass['name'] == 'Silver')
                or (member[3] == "Silver Membership - MPSF" and memberClass['name'] == 'Silver')
            ):
                # lookup in other landscapes
                lookupmember = Lookup.memberLandscape(member[0], member[2])
                item = {}
                if lookupmember:
                    for key, value in lookupmember.items():
                        item[key] = value
                else:
                    print("...Data from SFDC")
                    item = dict(item = None, name = member[0], logo = member[1], homepage_url = url_normalize(member[2]), crunchbase = Lookup.memberCrunchbase(member[0]))

                # Write out to missing.csv if it's missing key parameters
                if ( ( not item['crunchbase'] or 'https://www.crunchbase.com' not in item['crunchbase'] )
                    or ( not item['logo'] or not item['logo'].endswith('.svg') )
                    or ( not item['homepage_url'] or not validators.url(item['homepage_url']) ) ) :
                    print("...Missing key attributes - skip")
                    missingcsvwriter.writerow([item['name'],item['logo'],item['homepage_url'],item['crunchbase']])
                # otherwise we can add it
                else:
                    print("...Added to Landscape")
                    memberClass['items'].append(item)


# now write it back
for x in landscape['landscape']:
    if x['name'] == 'LF Member Company':
        x['subcategories'] = landscapeMembers

with open(landscapefile, 'w', encoding = "utf-8") as landscapefileoutput:
    landscapefileoutput.write( yaml.dump(landscape, default_flow_style=False, allow_unicode=True, Dumper=ruamel.yaml.RoundTripDumper) )

print("Successfully added "+str(countNew)+" LF members and updated "+str(countUpdates)+" member entries")
print("This took "+str(datetime.now() - startTime)+" seconds")

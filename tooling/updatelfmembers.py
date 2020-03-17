#!/usr/bin/env python
#
# Copyright this project and it's contributors
# SPDX-License-Identifier: Apache-2.0
#
# encoding=utf8

from ruamel import yaml
from url_normalize import url_normalize
import csv
import sys
import ruamel.yaml
import requests
from datetime import datetime
from bs4 import BeautifulSoup
startTime = datetime.now()

class Lookup:

    orglist = {}
    lfwebsitelist = []
    landscapes = {}

    # lookup entries for members in the other landscapes
    def landscape(company):

        normalizedCompany = Lookup.normalize(company)
        if not Lookup.landscapes:
            print("--Building landscape cache--")
            landscapeLocations = ['omp-landscape','aswf-landscape','lfdata-landscape','cncf-landscape']
            for landscape in landscapeLocations:
                landscapeFile = '../'+landscape+'/landscape.yml'
                landscapeYaml = yaml.load(open(landscapeFile, 'r', encoding="utf8", errors='ignore'), Loader=ruamel.yaml.RoundTripLoader)
                Lookup.landscapes[landscape] = landscapeYaml['landscape']

        # now iterate through all the landscapes
        for landscape in Lookup.landscapes:
            for category in Lookup.landscapes[landscape]:
                if 'Members' in category['name'] or 'Member Company' in category['name'] or 'Existing ODPi Members and other companies to invite' in category['name']:
                    for memberClass in category['subcategories']:
                        for landscapeMember in memberClass['items']:
                            landscapeMember['name'] = landscapeMember['name'].replace(' (member)','')
                            if landscapeMember['name'].replace(' (member)','') in [company,normalizedCompany] :
                                print("...Found in "+landscape+" - updating")
                                landscapeMember['logo'] = Lookup.logoURL(landscape,landscapeMember['logo'])
                                return landscapeMember

        return {}

    def lfwebsite(company, url):

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
            if entry['name'] == company:
                return dict(logo = entry['logo'], url = entry['url'])
            if entry['url'] == url:
                return dict(logo = entry['logo'], url = entry['url'])

        return {}

    def crunchbase(company):

        company = Lookup.normalize(company)

        if not Lookup.orglist:
            print("--Building Crunchbase cache--")
            crunchbasefile = 'organizations.csv'
            crunchbaselist = csv.reader(open(crunchbasefile, 'r', encoding="utf8", errors='ignore'))
            for organization in crunchbaselist:
                Lookup.orglist[organization[1]] = Lookup.normalize(organization[0])

            print(Lookup.orglist)

        print(company)

        for key, value in Lookup.orglist.items():
            if value == company:
                return "https://www.crunchbase.com/organization/"+key

        return ''

    def normalize(company):

        company = company.replace('.','')
        company = company.replace(' , Inc.','')
        company = company.replace(' Inc.','')
        company = company.replace(' AB','')
        company = company.replace(' Ltd','')
        company = company.replace(' , Ltd','')
        company = company.replace(' s.r.o.','')
        company = company.replace(' a.s.','')

        return company.strip()

    def logoURL(landscape, logo):

        if 'https://' in logo or 'http://' in logo:
            return logo

        if landscape == 'cncf-landscape' :
            return "https://github.com/cncf/landscape/raw/master/hosted_logos/"+logo
        if landscape == 'aswf-landscape' :
            return "https://github.com/AcademySoftwareFoundation/landscape/raw/master/hosted_logos/"+logo
        if landscape == 'omp-landscape' :
            return "https://github.com/openmainframeproject/landscape/raw/master/hosted_logos/"+logo
        if landscape == 'lfdata-landscape' :
            return "https://github.com/lfdata/lfdata-landscape/raw/master/hosted_logos/"+logo

# files we read/write from
sfdcfile = 'sfdcexport.csv'
landscapefile = 'landscape.yml'

memberslist = csv.reader(open(sfdcfile, 'r', encoding="utf8", errors='ignore'))
landscape = yaml.load(open(landscapefile, 'r', encoding="utf8", errors='ignore'), Loader=ruamel.yaml.RoundTripLoader)

# Find out where in the landscape yaml we should be doing updates
for x in landscape['landscape']:
    if x['name'] == 'LF Member Company':
        landscapeMembers = x['subcategories']

# Skip header
next(memberslist)

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
                lookupmember = Lookup.landscape(landscapeMember['name'])
                if lookupmember:
                    for key, value in lookupmember.items():
                        landscapeMember[key] = value
                    added += 1
                # lookup on LF lfwebsite
                lookupwebsite = Lookup.lfwebsite(landscapeMember['name'], landscapeMember['homepage_url'])
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
                    crunchbase = Lookup.crunchbase(member[0])
                    if crunchbase:
                        print("...Updating crunchbase")
                        landscapeMember['crunchbase'] = crunchbase
                        added += 1

                if added > 0:
                    countUpdates += 1

    if found == 0 and not 'test' in member[0] and not 'Test' in member[0]:
        # if not found, add it
        print("...Not in landscape - adding")
        countNew += 1
        for memberClass in landscapeMembers:
            #print(memberClass)
            if (( member[3] == "Associate Membership" and memberClass['name'] == 'Associate' )
                or (member[3] == "Gold Membership" and memberClass['name'] == 'Gold')
                or (member[3] == "Platinum Membership" and memberClass['name'] == 'Platinum')
                or (member[3] == "Silver Membership" and memberClass['name'] == 'Silver')
                or (member[3] == "Silver Membership - MPSF" and memberClass['name'] == 'Silver')
            ):
                item = dict(item = None, name = member[0], logo = member[1], homepage_url = url_normalize(member[2]), crunchbase = Lookup.crunchbase(member[0]))
                # lookup in other landscapes
                lookupmember = Lookup.landscape(member[0])
                if lookupmember:
                    item = lookupmember

                memberClass['items'].append(item)

# now write it back
for x in landscape['landscape']:
    if x['name'] == 'LF Member Company':
        x['subcategories'] = landscapeMembers

with open(landscapefile, 'w', encoding = "utf-8") as landscapefileoutput:
    landscapefileoutput.write( yaml.dump(landscape, default_flow_style=False, allow_unicode=True, Dumper=ruamel.yaml.RoundTripDumper) )

print("Successfully added "+str(countNew)+" LF members and updated "+str(countUpdates)+" member entries")
print("This took "+str(datetime.now() - startTime)+" seconds")

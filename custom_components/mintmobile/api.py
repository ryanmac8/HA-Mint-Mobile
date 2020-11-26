import requests

class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token
    def __call__(self, r):
        r.headers["authorization"] = "Bearer " + self.token
        return r

class MintMobile:
    def __init__(self, phone_number, password):
        self.phone_number = phone_number
        self.password = password
        self.token=""
        self.id=""
        self.family_members=[]
        self.info={}

    def login(self):
        #print("Logging Into " + self.phone_number)
        r=requests.post('https://w3b-api.ultramobile.com/v1/mint/login?', json = {"msisdn":self.phone_number,"password":self.password})
        if r.status_code == 200:
            response=r.json()
            self.id=response['id']
            self.token=response['token']
            self.info[self.id]={"phone_number":self.phone_number}
            self.master_line_name()
            return True
        else:
            return False



    def master_line_name(self):
        r=requests.get('https://w3b-api.ultramobile.com/v1/mint/account/'+str(self.id)+'?', auth=BearerAuth(str(self.token)))
        response=r.json()
        self.info[self.id]['line_name']=response['firstName']


    def data_remaining(self):
        r=requests.get('https://w3b-api.ultramobile.com/v1/mint/account/'+str(self.id)+'/data?', auth=BearerAuth(str(self.token)))
        response=r.json()
        response['remaining4G_GB']=self.conv_MB_to_GB(response['remaining4G'])
        self.info[self.id]['remaining4G']=response['remaining4G_GB']
        return self.info

    def conv_MB_to_GB(self,input_megabyte):
        gigabyte = 1.0/1024
        convert_gb = gigabyte * input_megabyte
        convert_gb=round(convert_gb, 2)
        return convert_gb

    def get_family_members(self):
        r=requests.get('https://w3b-api.ultramobile.com/v1/mint/account/'+str(self.id)+'/multi-line?', auth=BearerAuth(str(self.token)))
        response=r.json()
        for activeMembers in response['activeMembers']:
            self.family_members.append(activeMembers['id'])
            self.info[activeMembers['id']]={"phone_number":activeMembers['msisdn'],"line_name":activeMembers['nickName']}
        self.family_data_remaining()


    def family_data_remaining(self):
        for member in self.family_members:
            r=requests.get('https://w3b-api.ultramobile.com/v1/mint/account/'+self.id+'/multi-line/'+member+'/usage?', auth=BearerAuth(str(self.token)))
        response=r.json()
        response['remaining4G_GB']=self.conv_MB_to_GB(response['data']['remaining4G'])
        self.info[member]['remaining4G']=response['remaining4G_GB']

    def get_all_data_remaining(self):
        self.login()
        self.data_remaining()
        self.get_family_members()
        return self.info

    def lines(self):
        self.login()
        self.get_family_members()
        return self.info.keys()

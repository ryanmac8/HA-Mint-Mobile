from api import MintMobile
import pprint


pp = pprint.PrettyPrinter(indent=4)

username = input("Phone Number: ")
password = input("Enter Your Password: ")


mm = MintMobile(username,password)
print("Logging Into Mint Mobile.")
if mm.login():
    print("Login Successful")
else:
    print("Login Unsuccessful")

print("Printing All Mint Mobiles Found")
pp.pprint(mm.lines())

print("Printing Data From All Lines")
pp.pprint(mm.get_all_data_remaining())

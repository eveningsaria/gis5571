#imports
import arcpy
import requests
import zipfile
import io
import os
import pandas as pd

#recognize my map as the blank map that automatically loads in ArcGIS
aprx = arcpy.mp.ArcGISProject("CURRENT")
map = aprx.listMaps()[0]

#where all my files will go:
outputPath = r"C:\Documents\Projects\Lab1"

#the projection i will use
wgsRef = arcpy.SpatialReference(4326)

#request my data "from here"
mgsUrl = "https://resources.gisdata.mn.gov/pub/gdrs/data/pub/us_mn_state_dot/bdry_counties/shp_bdry_counties.zip"
res = requests.get(mgsUrl)

#check for success
if res.status_code == 200:
    print("Success!")
else:
    print("Error!")

#extracting the .zip file
ZIPfile = zipfile.ZipFile(io.BytesIO(res.content))
ZIPfile.extractall(outputPath)

#look for the .shp file
shapefiles = [file for file in os.listdir(outputPath) if file.endswith('.shp')]
for shp in shapefiles:
    print(f"{shp}")

#define variable to reach my .shp file
mgsFile = "County_Boundaries_in_Minnesota.shp" #name from above
mgsPath = os.path.join(outputPath, mgsFile)

#check for success
if os.path.exists(mgsPath):
    print("File saved to:", mgsPath)  
else:
    print("Error!")

#the URL i need to query
restUrl = "https://services.arcgis.com/8df8p0NlLFEShl0r/ArcGIS/rest/services/CountiesFreeReducedLunch2015to16/FeatureServer/0/query"

params = {
    "where": "1=1",  # Get all records
    "outFields": "*",  # Get all fields
    "f": "json"  # Return data
}

response = requests.get(restUrl, params=params)

#define variable to reach my .json file
restPath = os.path.join(outputPath, "CountiesFreeReducedLunch2015to16.json")

#check for success
if response.status_code == 200:
    if not os.path.exists(outputPath):
        os.makedirs(outputPath)
    with open(restPath, "w") as f:
        f.write(response.text)
    print("File saved to: ", restPath)
else:
    print("Error: ", response.status_code)

#i chose do use average temperature data across all the stations in Minnesota:
ndUrl = "https://ndawn.ndsu.nodak.edu/table.csv?station=78&station=174&station=118&station=87&station=124&station=226&station=219&station=184&station=2&station=220&station=223&station=93&station=183&station=156&station=70&station=173&station=185&station=187&station=119&station=4&station=82&station=225&station=120&station=71&station=103&station=116&station=114&station=3&station=115&station=121&station=61&station=181&station=60&station=122&station=5&station=91&station=182&station=117&station=6&station=222&station=92&station=123&station=95&station=148&variable=mdmxt&year=2024&ttype=monthly&quick_pick=&begin_date=2023-09&count=12"
#NDAWN exports data as a .csv. back in my comfort zone! let's make a place for that data in our project folder:
ndPath = os.path.join(outputPath, "weather_station_data.csv")

response = requests.get(ndUrl)

if response.status_code == 200:
    with open(ndPath, "wb") as f:  # Use 'wb' for binary mode
        f.write(response.content)
    print("File saved to: ", ndPath)
else:
    print("Error: ", response.status_code)

#list of my datasets to iterate over
datasets = [
    {"path": mgsPath, "name": "Minnesota Geospatial Commons"},
    {"path": restPath, "name": "Esri ARCGIS REST API"},
    {"path": ndPath, "name": "NDAWN"}
]

for dataset in datasets:
    path = dataset["path"]
    name = dataset["name"]

#define a function to reproject my spatial data not already in WGS 84
def reprojection(path, name):
    desc = arcpy.Describe(path)
    #check for spatial reference
    if hasattr(desc, 'spatialReference'): #if spatial reference
        if desc.spatialReference.name != wgsRef.name: #not in WGS84
            #make new file
            outputShp = f"{name.replace(' ', '_')}_WGS84.shp"
            shpPath = os.path.join(outputPath, outputShp)

            print(f"Projecting {name} to WGS 84...")
            arcpy.management.Project(path, shpPath, wgsRef)
            print("Projected file: ", shpPath)
        else: #already in WGS84
            print(name, " is already in WGS 84...")
    else: #no spatial reference
        outputTable = f"{name.replace(' ', '_')}_Table"
        arcpy.management.MakeTableView(path, outputTable)
        print(f"Added CSV {name} as table: {outputTable}")
        
#iterate over datasets
for dataset in datasets:
    reprojection(dataset["path"], dataset["name"])

#where my new file will go:
outputJoin = os.path.join(outputPath, "Joined_County_Data.shp")

#function to join data
def joinSpatial(spatialData, nonspatialData, spatialField, nonspatialField):
    table = os.path.join(outputPath, "restTable.dbf")
    
    #join data if input allows
    if arcpy.Exists(spatialData) & arcpy.Exists(nonspatialData):
        arcpy.conversion.JSONToFeatures(nonspatialData, (table))
        arcpy.management.JoinField(spatialData, spatialField, table, nonspatialField)
    
        #output shapefile
        arcpy.management.CopyFeatures(spatialData, outputJoin)
    
        print("Success! Saved to: ", outputJoin)
    else:
        print("Data error!")

#spatial join tiiiiiiiiiiiiiiiiiime
joinSpatial(mgsPath, restPath, "COUNTY_NAM", "Region")
#clean up because i made a messy shortcut and copied some stuff instead of being neat:
arcpy.management.Delete("County_Boundaries_in_Minnesota")

#make a function
def printHead(output):
    fields = [f.name for f in arcpy.ListFields(output)] #get field names
    rows = [] #make a list for my data
    
    #i was struggling to print a 2d table and got some help using SearchCursor. thank you to my data analyst sister!
    with arcpy.da.SearchCursor(output, fields) as cursor:
        for row in cursor:
            rows.append(row)

    df = pd.DataFrame(rows, columns=fields) #make a dataframe from that list
    print(df.head()) #and print

printHead(outputJoin)

for lyr in map.listLayers():
    if lyr.isFeatureLayer:  # Only export feature layers
        # Generate unique output path in the geodatabase
        gdbPath = os.path.join(outputPath, lyr.name.replace(" ", "_"))
        
        # Ensure the output name is unique
        if arcpy.Exists(gdbPath):
            print(gdbPath, " already exists. Skipping...")
        else:
            print("Saving", lyr.name)
            arcpy.management.CopyFeatures(lyr, gdbPath)
            print("Success! Saved to: ", gdbPath)



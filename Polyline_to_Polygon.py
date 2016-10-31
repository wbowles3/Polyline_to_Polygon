import arcpy
import itertools
import math
import os
import sys
import time
import datetime



# update_progress() : Displays or updates a console progress bar
## Accepts a float between 0 and 1. Any int will be converted to a float.
## A value under 0 represents a 'halt'.
## A value at 1 or bigger represents 100%
def update_progress(progress):
    barLength = 20 # Modify this to change the length of the progress bar
    status = ""
    if isinstance(progress, int):
        progress = float(progress)
    if not isinstance(progress, float):
        progress = 0
        status = "error: progress var must be float\r\n"
    if progress < 0:
        progress = 0
        status = "Halt...\r\n"
    if progress >= 1:
        progress = 1
        status = "Done...\r\n"
    block = int(round(barLength*progress))
    text = "\r\t\tPercent complete: [{0}] {1}% {2}".format( "="*block + " "*(barLength-block), progress*100, status)
    sys.stdout.write(text)
    sys.stdout.flush()


# Update user
start = datetime.datetime.now()
print '\nStarted program at', start


# Setup the temporary workspace and database if it doesn't exist
workspace = os.path.dirname(os.path.abspath(__file__))
temp_workspace = os.path.join(workspace, 'temp')
boundary = os.path.join(workspace, 'Townships.shp')
boundary_lyr = arcpy.MakeFeatureLayer_management(boundary, 'boundary_lyr')
sidewalks = os.path.join(workspace, 'HAM_SIDEWALKS.shp')
sidewalks_lyr = arcpy.MakeFeatureLayer_management(sidewalks, 'driveways_lyr')


# Create temporary workspace if it doesn't already exist
if not os.path.exists(temp_workspace):
    os.makedirs(temp_workspace)
    print '\nCreated temporary workspace.'


boundary_fields = ['BND_NAME', 'SIDEWALKS']
with arcpy.da.UpdateCursor(boundary_lyr, boundary_fields) as cursor:
    for bnd in cursor:
        if not bnd[1]:
            boundary_name = bnd[0]
            sql = '"BND_NAME" = \'' + boundary_name + '\''
            arcpy.SelectLayerByAttribute_management(boundary_lyr, 'NEW_SELECTION', sql)


            # Update User
            print '\nSearching', boundary_name, 'for driveway lines...'


            arcpy.SelectLayerByLocation_management(sidewalks_lyr, 'WITHIN', boundary_lyr, '', 'NEW_SELECTION')


            # Update User
            print '\tCollecting endpoints from', boundary_name, 'driveway lines...'


            # Get start and end points from selected features
            endpoints = []
            fields = ['SHAPE@']
            for row in arcpy.da.SearchCursor(sidewalks_lyr, fields):
                try:
                    # Collect all start points
                    start_point = row[0].firstPoint
                    start_point = str(start_point).split(' ')
                    start_point = float(start_point[0]), float(start_point[1])
                    endpoints.append(start_point)
                    del start_point
                    # Collect all endpoints
                    endpoint = row[0].lastPoint
                    endpoint = str(endpoint).split(' ')
                    endpoint = float(endpoint[0]), float(endpoint[1])
                    endpoints.append(endpoint)
                    del endpoint
                    del row
                except:
                    pass
            del fields


            # Update user
            print '\tFinished collecting endpoints.'
            print '\tNumber of endpoints found in', boundary_name + ':', len(endpoints)
            print '\tComparing endpoints to one another...'


            # Define distance function
            def distance(point_1, point_2):
                return math.sqrt((point_1[0] - point_2[0]) ** 2 + (point_1[1] - point_2[1]) ** 2)

            # Compare endpoints and find closest pairs
            step_count = 2
            total_endpoints = len(endpoints)
            temp_file_list = []
            line_array = arcpy.Array()
            while len(endpoints) > 0:
                update_progress(float(step_count) / float(total_endpoints))
                minimum_distance = float('inf')
                for point_1, point_2 in itertools.combinations(endpoints, 2):
                    if distance(point_1, point_2) < minimum_distance:
                        minimum_distance = distance(point_1, point_2)
                        closest_pair = (point_1, point_2)
                    del point_1, point_2

                # Add first point from closest pair to line array
                closest_point_1 = closest_pair[0]
                x1 = closest_point_1[0]
                y1 = closest_point_1[1]
                line_array.add(arcpy.Point(x1, y1))
                endpoints.remove(closest_point_1)
                del closest_point_1, x1, y1

                # Add second point from closest pair to line array
                closest_point_2 = closest_pair[1]
                x2 = closest_point_2[0]
                y2 = closest_point_2[1]
                line_array.add(arcpy.Point(x2, y2))
                endpoints.remove(closest_point_2)
                del closest_point_2, x2, y2
                del closest_pair

                # Create line using two new points
                polyline = arcpy.Polyline(line_array)
                temp_name = 'temp' + str(step_count) + '.shp'
                output_test = os.path.join(temp_workspace, temp_name)
                arcpy.CopyFeatures_management(polyline, output_test)
                temp_file_list.append(output_test)
                line_array.removeAll()
                step_count += 2

                #print '\t\tNumber of endpoints left in', boundary_name + ':', len(endpoints)
            del endpoints, line_array


            # Update User
            print '\tDone comparing endpoints.'
            print '\tNumber of lines created for', boundary_name + ':', len(temp_file_list)
            print '\tMerging original lines together...'


            # Merge selected lines into one shapefile
            temp_selection_merge = os.path.join(temp_workspace, 'temp_selection_merge.shp')
            arcpy.Merge_management(sidewalks_lyr, temp_selection_merge)
            temp_file_list.append(temp_selection_merge)  # Add to list to delete later


            # Update User
            print '\tDone merging original lines!'
            print '\tMerging original lines with new lines...'


            # Merge selected lines and new lines into one shapefile
            final_merge = os.path.join(temp_workspace, 'temp_merge.shp')
            arcpy.Merge_management(temp_file_list, final_merge)
            temp_file_list.append(final_merge)

            # Update User
            print '\tDone merging all lines!'
            print '\tDissolving all lines into one feature...'


            # Dissolve all line parts to correct drawing order
            temp_dissolve = os.path.join(temp_workspace, 'temp_dissolve.shp')
            arcpy.Dissolve_management(final_merge, temp_dissolve)
            temp_file_list.append(temp_dissolve)

            # Update User
            print '\tDone merging all lines into one feature!'
            print '\tSplitting individual driveways up...'


            # Divide the dissolve out into individual driveways
            temp_multipart = os.path.join(temp_workspace, 'temp_multipart.shp')
            arcpy.MultipartToSinglepart_management(temp_dissolve, temp_multipart)
            temp_file_list.append(temp_multipart)


            # Update User
            print '\tDone splitting driveways!'
            print '\tCreating new polygon shapefile'


            shapefile_name = boundary_name + '_Sidewalk_Polygons.shp'
            polygon_output = os.path.join(workspace, shapefile_name)
            if arcpy.Exists(polygon_output):
                arcpy.Delete_management(polygon_output)
            arcpy.CreateFeatureclass_management(workspace, shapefile_name, 'POLYGON')


            # Update User
            print '\tDone creating polygon shapefile'
            print '\tBuilding polygons from individual driveways...'


            # Draw new polygon using the dissolved line
            line_array = arcpy.Array()
            fields = ['SHAPE@']
            for row in arcpy.da.SearchCursor(temp_multipart, fields):
                for part in row[0]:
                    for pnt in part:
                        if pnt:
                            line_array.add(arcpy.Point(pnt.X, pnt.Y))
                        del pnt
                    del part
                del row
                polygon = arcpy.Polygon(line_array)
                insert_polygon = arcpy.da.InsertCursor(polygon_output, fields)
                insert_polygon.insertRow([polygon])
                line_array.removeAll()
                del polygon
            del line_array


            # Update User
            print '\tFinished building polygons!'
            print '\tDeleting temporary files...'


            # Delete all the temp files
            for temp_file in temp_file_list:
                if arcpy.Exists(temp_file):
                    arcpy.Delete_management(temp_file)

            bnd[1] = 'Yes'
            cursor.updateRow(bnd)
            print '\tCompleted driveways in', boundary_name
        del bnd

end = datetime.datetime.now()
total_time = start - end
# Update User
print '\n\nProgram complete!'
print '\nTotal Time:', total_time
raw_input('\nPress ENTER to exit.')

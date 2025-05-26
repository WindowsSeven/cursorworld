import asyncio
import websockets
import json
import random
import os
import base64

DATA_FILE = "cursor_data.txt"
IMAGE_DIR = "images"

connected_clients = {}
available_images = set()  # Keep track of available images
client_image_map = {}  # Map client IDs to the images they uploaded

# Helper function to write data to the file
def write_data_to_file(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error writing to file: {e}")

# Helper function to read data from the file
def read_data_from_file():
    try:
        if os.path.exists(DATA_FILE):  # Check if file exists
            with open(DATA_FILE, "r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    print("Warning: File is empty or contains invalid JSON.")
                    return {}  # Return an empty dictionary if the file is empty or invalid
        else:
            print("File does not exist. Creating a new file.")
            return {}  # Return an empty dictionary if the file doesn't exist
    except Exception as e:
        print(f"Error reading from file: {e}")
        return {}  # Return an empty dictionary in case of an error

# Ensure the image directory exists
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

# Load existing images on server start
for filename in os.listdir(IMAGE_DIR):
    available_images.add(filename)

async def handle_client(websocket):  # Corrected: Removed the 'path' argument
    client_id = None
    try:
        async for message in websocket:
            data = json.loads(message)

            if data['type'] == 'newPlayer':
                client_id = data['id']
                initial_color = data["color"]  # Get the color from the front end
                initial_username = data.get("username", "")  # Get the username from the front end

                # Check if user exists
                if client_id in connected_clients:  # IF the user already exists, then, skip adding again. Just replace its thing
                    connected_clients[client_id]["websocket"] = websocket  # Set the websocket
                else:
                    connected_clients[client_id] = {"websocket": websocket, "x": 0, "y": 0, "color": initial_color, "scale": 1, "username": initial_username}  # Set the initial Color and Username for the initial user
                    print(f"New client connected: {client_id}")

                # Send the new client the list of all *existing* players, along with their coordinates, AND COLOR!
                player_list = {}
                for id, client_data in connected_clients.items():
                    if id != client_id:
                        player_list[id] = {'x': client_data["x"], 'y': client_data["y"], 'color': client_data["color"], 'scale': client_data["scale"], 'username': client_data["username"]}

                # Send the list of available images to the new client
                await websocket.send(json.dumps({
                    'type': 'playerList',
                    'players': player_list,
                    'images': list(available_images)  # Send images on connect
                }))

                # Notify all *other* clients about the new player, include color and position
                for id, client_data in connected_clients.items():
                    if id != client_id:
                        try:
                            await client_data["websocket"].send(json.dumps({'type': 'newPlayer', 'id': client_id, 'x': connected_clients[client_id]["x"], 'y': connected_clients[client_id]["y"], 'color': initial_color, 'scale': connected_clients[client_id]["scale"], 'username': initial_username}))  # Pass the old parameters
                        except websockets.exceptions.ConnectionClosed:
                            print(f"Client {id} disconnected unexpectedly.")
                            del connected_clients[id]

                # Write data to file, excluding websocket objects
                write_data_to_file({k: {key: val for key, val in v.items() if key != 'websocket'} for k, v in connected_clients.items()})

            elif data['type'] == 'cursorMove':
                x = data['x']
                y = data['y']
                scale = data.get('scale', 1)  # Get the scale, default to 1 if not provided
                # Update the server's stored position and scale for the client
                connected_clients[client_id]["x"] = x
                connected_clients[client_id]["y"] = y
                connected_clients[client_id]["scale"] = scale

                # Broadcast the cursor movement and scale to *all* other clients
                for id, client_data in connected_clients.items():
                    if id != client_id:
                        try:
                            await client_data["websocket"].send(json.dumps({'type': 'updateCursor', 'id': client_id, 'x': x, 'y': y, 'scale': scale}))
                        except websockets.exceptions.ConnectionClosed:
                            print(f"Client {id} disconnected unexpectedly.")
                            del connected_clients[id]

                # Write data to file, excluding websocket objects
                write_data_to_file({k: {key: val for key, val in v.items() if key != 'websocket'} for k, v in connected_clients.items()})

            elif data['type'] == 'newColor':  # handles new color event, and send to all clients
                client_id = data['id']
                new_color = data["color"]
                connected_clients[client_id]["color"] = new_color  # save
                # Broadcast the cursor movement to *all* other clients
                for id, client_data in connected_clients.items():
                    if id != client_id:
                        try:
                            await client_data["websocket"].send(json.dumps({'type': 'newColor', 'id': client_id, 'color': new_color}))
                        except websockets.exceptions.ConnectionClosed:
                            print(f"Client {id} disconnected unexpectedly.")
                            del connected_clients[id]

                # Write data to file, excluding websocket objects
                write_data_to_file({k: {key: val for key, val in v.items() if key != 'websocket'} for k, v in connected_clients.items()})

            elif data['type'] == 'uploadImage':
                image_data = data['imageData']
                image_name = data['imageName']
                image_path = os.path.join(IMAGE_DIR, image_name)

                # Save the image to the server
                try:
                    with open(image_path, "wb") as f:
                        f.write(base64.b64decode(image_data.split(',')[1]))
                    available_images.add(image_name)
                    client_image_map[client_id] = image_name  # Store the mapping
                    print(f"Image uploaded: {image_name} by client {client_id}")
                except Exception as e:
                    print(f"Error saving image: {e}")
                    continue

                # Notify all clients about the new image
                for id, client_data in connected_clients.items():
                    try:
                        await client_data["websocket"].send(json.dumps({'type': 'newImage', 'id': client_id, 'imageName': image_name}))
                    except websockets.exceptions.ConnectionClosed:
                        print(f"Client {id} disconnected unexpectedly.")
                        del connected_clients[id]

            elif data['type'] == 'newUsername':  # handles new username event, and send to all clients
                client_id = data['id']
                new_username = data["username"]
                connected_clients[client_id]["username"] = new_username  # save
                # Broadcast the new username to *all* other clients
                for id, client_data in connected_clients.items():
                    if id != client_id:
                        try:
                            await client_data["websocket"].send(json.dumps({'type': 'newUsername', 'id': client_id, 'username': new_username}))
                        except websockets.exceptions.ConnectionClosed:
                            print(f"Client {id} disconnected unexpectedly.")
                            del connected_clients[id]

                # Write data to file, excluding websocket objects
                write_data_to_file({k: {key: val for key, val in v.items() if key != 'websocket'} for k, v in connected_clients.items()})

            elif data['type'] == 'chatMessage':  # handles chat messages and broadcasts them to all clients
                client_id = data['id']
                message = data['message']
                username = connected_clients[client_id]["username"]
                # Broadcast the chat message to *all* clients
                for id, client_data in connected_clients.items():
                    try:
                        await client_data["websocket"].send(json.dumps({'type': 'chatMessage', 'username': username, 'message': message}))
                    except websockets.exceptions.ConnectionClosed:
                        print(f"Client {id} disconnected unexpectedly.")
                        del connected_clients[id]

            elif data['type'] == 'playerDisconnected':
                if client_id in connected_clients:
                    # Delete the image if this client uploaded it
                    if client_id in client_image_map:
                        image_to_delete = client_image_map[client_id]
                        image_path = os.path.join(IMAGE_DIR, image_to_delete)
                        try:
                            os.remove(image_path)
                            print(f"Deleted image: {image_to_delete}")
                            available_images.discard(image_to_delete)  # Remove from available files
                        except FileNotFoundError:
                            print(f"Image not found: {image_to_delete}")
                        except Exception as e:
                            print(f"Error deleting image: {e}")
                        del client_image_map[client_id]  # Remove from mapping

                    del connected_clients[client_id]

                    # Write data to file, excluding websocket objects
                    write_data_to_file({k: {key: val for key, val in v.items() if key != 'websocket'} for k, v in connected_clients.items()})

    except websockets.exceptions.ConnectionClosedError:
        print(f"Client {client_id} disconnected.")
    finally:
        if client_id in connected_clients:
            del connected_clients[client_id]
            print(f"Client disconnected: {client_id}")

            # Notify all other clients about the disconnected player
            for id, client_data in connected_clients.items():
                try:
                    await client_data["websocket"].send(json.dumps({'type': 'playerDisconnected', 'id': client_id}))
                except websockets.exceptions.ConnectionClosed:
                    print(f"Client {id} disconnected unexpectedly during disconnect broadcast.")
                    del connected_clients[id]

            # Clean up unused images
            clean_up_unused_images()

            # Write data to file, excluding websocket objects
            write_data_to_file({k: {key: val for key, val in v.items() if key != 'websocket'} for k, v in connected_clients.items()})

def clean_up_unused_images():
    used_images = set(client_image_map.values())
    print(f"Used images: {used_images}")
    print(f"Available images: {available_images}")
    for image in available_images:
        if image not in used_images:
            image_path = os.path.join(IMAGE_DIR, image)
            try:
                os.remove(image_path)
                print(f"Deleted unused image: {image}")
                available_images.discard(image)
            except FileNotFoundError:
                print(f"Unused image not found: {image}")
            except Exception as e:
                print(f"Error deleting unused image: {e}")

async def main():
    async with websockets.serve(handle_client, "0.0.0.0", 8765):  # Corrected: No more path argument.
        print("WebSocket server started at ws://0.0.0.0:8765")
        await asyncio.Future()  # Run forever

# Start the server
if __name__ == "__main__":
    asyncio.run(main())

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.responses import JSONResponse
from typing import Union, List
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from fastapi.encoders import jsonable_encoder
import dns.resolver
dns.resolver.default_resolver=dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers=['8.8.8.8']

app = FastAPI()

# MongoDB Atlas connection details
MONGO_CONNECTION_STRING = "mongodb+srv://<username>:<password>@cluster0.mongodb.net/books?retryWrites=true&w=majority"
                           
DATABASE_NAME = "bookstore"
COLLECTION_NAME = "books"

# Pydantic model for the book
class BookModel(BaseModel):
    title: str
    author: str
    genre: str
    price: float

# Connect to MongoDB
mongo_client = AsyncIOMotorClient(MONGO_CONNECTION_STRING)
database = mongo_client[DATABASE_NAME]
books_collection = database[COLLECTION_NAME]

@app.post("/api/books")
async def create_book(book: BookModel = Body(...)):
    # Convert Pydantic model to a dictionary
    book_dict = book.dict()

    # Insert the book into the MongoDB collection
    result = await books_collection.insert_one(book_dict)

    # Check if insertion was successful
    if result.inserted_id:
        return {"message": "Book created successfully", "book_id": str(result.inserted_id)}
    else:
        raise HTTPException(status_code=500, detail="Failed to create book")
    


class CustomJSONResponse(JSONResponse):
    def render(self, content: Union[str, bytes, dict, List[dict]]) -> bytes:
        if isinstance(content, list):
            # If content is a list, encode each item separately
            content = [jsonable_encoder(item, by_alias=True) for item in content]
        else:
            content = jsonable_encoder(content, by_alias=True)
        return super().render(content)

async def get_books(
    book_id: str = Query(None, description="Book ID to filter by"),
    author: str = Query(None, description="Author to filter by"),
    genre: str = Query(None, description="Genre to filter by"),
    min_price: float = Query(None, description="Minimum price to filter by"),
    max_price: float = Query(None, description="Maximum price to filter by")
):
    try:
        # Convert the book_id to ObjectId if provided
        if book_id:
            book_id_object = ObjectId(str(book_id))
        else:
            book_id_object = None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid book_id format")

    # Construct query based on provided parameters
    query = {}
    if book_id_object:
        query["_id"] = book_id_object
    if author:
        query["author"] = author
    if genre:
        query["genre"] = genre
    if min_price is not None:
        query["price"] = {"$gte": min_price}
    if max_price is not None:
        query.setdefault("price", {}).update({"$lte": max_price})

    # Define projection to exclude "_id" field
    projection = {"_id": 0}

    # Retrieve the list of books from the MongoDB collection based on the query
    cursor = books_collection.find(query, projection=projection)
    books = await cursor.to_list(length=None)

    # If no parameters are provided, return the total book list
    if not any((book_id, author, genre, min_price, max_price)):
        all_books_cursor = books_collection.find({}, projection=projection)
        all_books = await all_books_cursor.to_list(length=None)
        return all_books

    return books

@app.get("/api/books", response_class=CustomJSONResponse)
async def wrapper_get_books(
    book_id: str = Query(None, description="Book ID to filter by"),
    author: str = Query(None, description="Author to filter by"),
    genre: str = Query(None, description="Genre to filter by"),
    min_price: float = Query(None, description="Minimum price to filter by"),
    max_price: float = Query(None, description="Maximum price to filter by")
):
    return await get_books(book_id, author, genre, min_price, max_price)



@app.get("/api/books/{book_id}")
async def get_book(book_id: str):
    try:
        # Convert the book_id to ObjectId
        book_id_object = ObjectId(book_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid book_id format")

    # Retrieve the book from the MongoDB collection
    book = await books_collection.find_one({"_id": book_id_object})

    if book:
        # Convert the ObjectId to a string for serialization
        book['_id'] = str(book['_id'])
        book_dict = jsonable_encoder(book)
        return book_dict
    else:
        raise HTTPException(status_code=404, detail="Book not found")
    


@app.put("/api/books/{book_id}")
async def update_book(book_id: str, book: BookModel = Body(...)):
    try:
        # Convert the book_id to ObjectId
        book_id_object = ObjectId(book_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid book_id format")

    # Convert Pydantic model to a dictionary
    book_dict = jsonable_encoder(book)

    # Update the book in the MongoDB collection
    result = await books_collection.update_one({"_id": book_id_object}, {"$set": book_dict})

    # Check if update was successful
    if result.modified_count == 1:
        return {"message": "Book updated successfully"}
    else:
        raise HTTPException(status_code=404, detail="Book not found")
from fastapi import APIRouter, HTTPException, status, Depends
from app.models.user import UserCreate, UserLogin, UserResponse, UserInDB, Device
from app.core.database import db_instance
from app.core.security import get_password_hash, verify_password, create_access_token, get_current_user
from app.api.dependencies import verify_api_key
from app.models.user import FCMTokenRequest
import uuid

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate, api_key: str = Depends(verify_api_key)):
    # 1. Check if username exists
    existing_user = await db_instance.users.find_one({"username": user_data.username}) # type: ignore
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    # 2. SECURITY FIX: Prevent ID Collision / Account Takeover
    # Check if the provided user_id is already taken by someone else!
    if user_data.user_id:
        existing_id = await db_instance.users.find_one({"user_id": user_data.user_id}) # type: ignore
        if existing_id:
            raise HTTPException(status_code=400, detail="User ID collision. Please generate a new account.")

    # 3. Use the frontend's UUID if they provided one, otherwise generate a new one
    user_id = user_data.user_id if user_data.user_id else str(uuid.uuid4())
    
    hashed_pwd = get_password_hash(user_data.password)
    
    initial_device = Device(
        device_id=str(uuid.uuid4()),
        public_key=user_data.public_key,
        device_name="Primary Device",
        is_active=True
    )
    
    new_user = UserInDB(
        user_id=user_id, # <-- Now using the preserved ID securely
        username=user_data.username,
        hashed_password=hashed_pwd,
        devices=[initial_device],
        public_key=user_data.public_key,
        private_key=user_data.private_key
    )

    await db_instance.users.insert_one(new_user.model_dump()) # type: ignore

    return new_user

@router.post("/login")
async def login_user(user_data: UserLogin, api_key: str = Depends(verify_api_key)):
    user = await db_instance.users.find_one({"username": user_data.username}) # type: ignore
    
    if not user or not verify_password(user_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid username or password"
        )

    access_token = create_access_token(subject=user["user_id"])
    
    # Return BOTH keys to the app so it can decrypt old messages!
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "user_id": user["user_id"],
        "public_key": user.get("public_key", ""),
        "private_key": user.get("private_key", "")
    }
    
@router.get("/user/{username}", response_model=UserResponse)
async def get_user_by_username(username: str, api_key: str = Depends(verify_api_key)):
    user = await db_instance.users.find_one({"username": username}) # type: ignore
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="User not found"
        )
        
    return UserResponse(**user)

@router.post("/fcm-token")
async def update_fcm_token(
    request: FCMTokenRequest,
    current_user_id: str = Depends(get_current_user) # This gets the user ID from your JWT
):
    # Grab the users collection directly from your db_instance
    users_collection = db_instance.users
    
    # Update the user's document in MongoDB with their new device token
    result = await users_collection.update_one( #type: ignore
        {"user_id": current_user_id},
        {"$set": {"fcm_token": request.fcm_token}}
    )
    
    if result.modified_count == 1:
        return {"status": "success", "message": "FCM token updated"}
    return {"status": "success", "message": "FCM token was already up to date"}


@router.get("/public-key/{target_user_id}")
async def get_public_key(target_user_id: str):
    # Find the user in the database
    user = await db_instance.users.find_one({"user_id": target_user_id}) # type: ignore
    
    if not user or not user.get("public_key"):
        raise HTTPException(status_code=404, detail="Public key not found for this user")
        
    return {
        "user_id": target_user_id, 
        "public_key": user["public_key"]
    }
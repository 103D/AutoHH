import pytest

from httpx import ASGITransport, AsyncClient
from uuid import uuid4

from app.main import app

@pytest.mark.asyncio
async def test_create_profile():
    """Test creating candidate profile."""
    user_id = uuid4()
    
    profile_data = {
        "user_id": str(user_id),
        "desired_positions": ["Data Analyst", "BI Analyst"],
        "skills": ["SQL", "Python", "Tableau"],
        "technologies": {
            "languages": ["Python", "SQL"],
            "databases": ["PostgreSQL", "MongoDB"],
            "tools": ["Tableau", "Power BI"]
        },
        "experience_years": 3,
        "experience_level": "middle",
        "languages": {
            "Russian": "native",
            "English": "B2",
            "Kazakh": "intermediate"
        },
        "location": "Almaty",
        "desired_salary_min": 400000,
        "desired_salary_max": 600000,
        "salary_currency": "KZT",
        "employment_types": ["full_time"],
        "work_formats": ["remote", "hybrid"],
        "relocation_possible": False,
        "business_trips_acceptable": True,
    }
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/profile/", json=profile_data)
        
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["user_id"] == str(user_id)
        assert data["desired_positions"] == profile_data["desired_positions"]
        assert data["experience_years"] == 3

@pytest.mark.asyncio
async def test_get_profile():
    """Test getting candidate profile."""
    user_id = uuid4()
    
    profile_data = {
        "user_id": str(user_id),
        "desired_positions": ["Data Analyst"],
        "skills": ["SQL"],
        "languages": {"English": "B2"},
    }
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # Create
        create_response = await client.post("/api/v1/profile/", json=profile_data)
        assert create_response.status_code == 201
        created_data = create_response.json()
        profile_id = created_data["id"]
        
        # Get by ID
        get_response = await client.get(f"/api/v1/profile/{profile_id}")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["id"] == profile_id
        
        # Get by user_id
        get_by_user_response = await client.get(f"/api/v1/profile/?user_id={user_id}")
        assert get_by_user_response.status_code == 200
        get_by_user_data = get_by_user_response.json()
        assert get_by_user_data["user_id"] == str(user_id)

@pytest.mark.asyncio
async def test_update_profile():
    """Test updating candidate profile."""
    user_id = uuid4()
    
    profile_data = {
        "user_id": str(user_id),
        "desired_positions": ["Data Analyst"],
        "skills": ["SQL"],
        "languages": {"English": "B2"},
        "experience_years": 2,
    }
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # Create
        create_response = await client.post("/api/v1/profile/", json=profile_data)
        profile_id = create_response.json()["id"]
        
        # Update
        update_data = {
            "experience_years": 3,
            "skills": ["SQL", "Python", "Tableau"],
        }
        update_response = await client.put(f"/api/v1/profile/{profile_id}", json=update_data)
        assert update_response.status_code == 200
        updated_data = update_response.json()
        assert updated_data["experience_years"] == 3
        assert len(updated_data["skills"]) == 3

@pytest.mark.asyncio
async def test_delete_profile():
    """Test deleting candidate profile."""
    user_id = uuid4()
    
    profile_data = {
        "user_id": str(user_id),
        "desired_positions": ["Data Analyst"],
        "skills": ["SQL"],
        "languages": {"English": "B2"},
    }
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # Create
        create_response = await client.post("/api/v1/profile/", json=profile_data)
        profile_id = create_response.json()["id"]
        
        # Delete
        delete_response = await client.delete(f"/api/v1/profile/{profile_id}")
        assert delete_response.status_code == 204
        
        # Verify deleted
        get_response = await client.get(f"/api/v1/profile/{profile_id}")
        assert get_response.status_code == 404

@pytest.mark.asyncio
async def test_duplicate_profile():
    """Test creating duplicate profile fails."""
    user_id = uuid4()
    
    profile_data = {
        "user_id": str(user_id),
        "desired_positions": ["Data Analyst"],
        "skills": ["SQL"],
        "languages": {"English": "B2"},
    }
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # Create first
        response1 = await client.post("/api/v1/profile/", json=profile_data)
        assert response1.status_code == 201
        
        # Try to create duplicate
        response2 = await client.post("/api/v1/profile/", json=profile_data)
        assert response2.status_code == 409
//! Pomocník pro `serde`: hodnota se ukládá jako text JSON.
//!
//! Kontrolní body používají kompaktní formát bez popisu typů (postcard), který neumí
//! `serde_json::Value`. Pole s volným JSON obsahem se proto označí
//! `#[serde(with = "crate::json_string")]` a ukládají se jako řetězec.

use serde::de::DeserializeOwned;
use serde::{Deserialize, Deserializer, Serialize, Serializer};

pub fn serialize<T: Serialize, S: Serializer>(value: &T, serializer: S) -> Result<S::Ok, S::Error> {
    serializer.serialize_str(&serde_json::to_string(value).map_err(serde::ser::Error::custom)?)
}

pub fn deserialize<'de, T: DeserializeOwned, D: Deserializer<'de>>(deserializer: D) -> Result<T, D::Error> {
    let text = String::deserialize(deserializer)?;
    serde_json::from_str(&text).map_err(serde::de::Error::custom)
}

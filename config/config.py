import json


class Config:
    def __init__(self, file_loc: str,
                 required_keys: dict = None,
                 autosave: bool = False,
                 delay_load: bool = False):
        """
        Creates a Config object and loads the values in from the provided file path

        :param file_loc: The path to the JSON file
        :param required_keys: A dictionary of the keys required to be present in the
            configuration file
                - key: (str) The name of required key
                - value: (type) The type of the data in the key. If the data is not of
                    that type, one will be constructed using the value as the parameter
        :param autosave: Whether to automatically save the configuration file after
            updating a value
        :param delay_load: Set to `True` to prevent the constructor from loading the
            config file
        """
        self.autosave = autosave
        self.file_loc = file_loc
        self.required_keys = required_keys if required_keys is not None else {}
        self.values = {}
        if not delay_load:
            self.reload()

    def __getitem__(self, key):
        """
        Allows config values to be directly accessed via key (e.g. config['value']) rather than
        needing to first access self.values

        :param key: The key being accessed
        :return: The attribute stored in the key
        """
        return self.values[key]

    def __contains__(self, key) -> bool:
        """
        Allows for key checking directly from Config, rather than Config.values

        :param key: The key being checked
        :return: `True` if Config contains `key`
        """
        return key in self.values

    def require_keys(self, keys: dict) -> None:
        """
        Sets the keys and the type expected. If the value found in a configuration
        file does not match the expected type, the value found will be passed to
        that type's constructor and the resulting object will be used.

        :param keys: A <str: type> dictionary of the required keys and their expected
            types. If any type is allowed for a key, use `None`
        :raises ValueError: A value in the dictionary is neither a type nor `None`
        """
        for (key, value) in keys.items():
            if not isinstance(value, type) and value is not None:
                raise ValueError(f"Found non-type value `{value}` for the key `{key}`")
        self.required_keys = keys

    def reload(self, required_keys: dict = None) -> None:
        """
        Reads in configuration values from file. Any existing configuration
        values will be overwritten. If a required key is missing, or the value
        for any required key is of the wrong type and cannot be cast to the
        provided type, an exception will be raised and the configuration values
        will not be updated

        :param required_keys: If provided, overrides the
        :raises RuntimeError: If a required key is missing
        :raises TypeError: If a required key's value is not the specified type
            and its constructor won't accept the value as an argument
        """
        if required_keys is None:
            required_keys = self.required_keys

        with open(self.file_loc) as json_file:
            new_values = json.load(json_file)

        for (key, expected_type) in required_keys.items():  # Check to make sure all required keys are present
            if expected_type is not None:  # Ignore type check if type is `None`
                if key not in new_values:  # Raise error if key could not be found
                    raise RuntimeError(f"Missing required configuration key: `{key}` ({expected_type.__name__})")
                else:
                    try:  # Cast value to required type
                        new_values[key] = expected_type(new_values[key])
                    except Exception as exc:  # If cast fails for any reason, raise a TypeError
                        raise TypeError(f"Failed to cast the value of key `{key}` "
                                        f"from {new_values[key].__name__} to {expected_type.__name__}\n{exc}")
        self.values.update(new_values)

    def save(self, all_values: bool = True) -> None:
        """
        Saves the configuration values to file.

        :param all_values: If `True`, all present config values will be written to file.
                If `False`, only the keys present in the target file will be overwritten
        """

        """ Read values in target file """
        with open(self.file_loc) as json_file:
            file_values = json.load(json_file)

        """ Update dictionary files """
        if all_values:  # Copy all values
            file_values.update(self.values)
        else:           # Only update keys present in target file
            for key in self.values:     # Check all configuration keys
                if key in file_values:  # Update if key is in file
                    file_values[key] = self.values[key]

        """ Save updated dictionary to file """
        with open(self.file_loc, 'w') as json_file:
            json.dump(file_values, json_file, indent=2)

    def set_value(self, key: str, value) -> None:
        """
        Inserts a value into the configuration dictionary if not present, otherwise
        updates the existing value.

        :param key: The key for the configuration value
        :param value: The value to insert
        :raises TypeError: If the key is required but the value is not the expected type
        """
        if key in self.required_keys \
                and self.required_keys[key] is not None \
                and not isinstance(value, self.required_keys[key]):
            try:
                value = self.required_keys[key](value)
            except Exception as exc:
                raise TypeError(f"Could not convert value for required key {key} to expected type "
                                f"{self.required_keys[key].__name__}\n{exc}")
        self.values[key] = value
        if self.autosave:
            self.save(all_values=False)


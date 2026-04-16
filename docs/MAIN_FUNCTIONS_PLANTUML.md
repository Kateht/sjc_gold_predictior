# Main Function Activity Diagrams

This document contains PlantUML activity diagrams for the main functions in the system.
All diagrams are written in English and each one ends with a single `stop` node.

## 4.3.1 Authentication Module

```plantuml
@startuml
title 4.3.1 Authentication Module

start
:Open the authentication screen;
if (User selects login?) then (yes)
  :Enter email and password;
  :Submit the login request;
  if (Credentials are valid?) then (yes)
    :Issue the access token and refresh token;
    :Persist the session data;
    :Load the current user profile;
  else (no)
    :Display the login error message;
  endif
else (register)
  :Enter name, email, and password;
  :Submit the registration request;
  if (Registration data is valid?) then (yes)
    :Create the user account;
    :Issue the access token and refresh token;
    :Persist the session data;
    :Load the current user profile;
  else (no)
    :Display the registration error message;
  endif
endif
:Return the authentication result to the UI;
stop

@enduml
```

## 4.3.2 Dashboard Module

```plantuml
@startuml
title 4.3.2 Dashboard Module

start
:Open the dashboard page;
:Request overview data, models, news, and gold sources in parallel;
if (Critical dashboard data is loaded?) then (yes)
  :Store the overview and model data;
else (no)
  :Show a dashboard error banner;
endif
if (News request failed?) then (yes)
  :Keep the dashboard visible with a news error state;
endif
:Request the price chart using the selected source and range;
if (Compare mode is enabled?) then (yes)
  :Load both SJC and world chart series;
  :Align the series by date;
else (no)
  :Load a single chart series;
endif
if (Custom range is enabled for an authenticated user?) then (yes)
  :Filter the chart by the selected date range;
endif
:Render metrics, charts, source cards, model cards, and news cards;
stop

@enduml
```

## 4.3.3 Trend Prediction Module

```plantuml
@startuml
title 4.3.3 Trend Prediction Module

start
:Open trend prediction mode;
:Select the source, range, model, and forecast horizon;
:Load historical prices for the selected source;
:Limit the history to the chosen range;
if (Requested model is available?) then (yes)
  :Use the selected trend model;
else (no)
  :Use fallback trend metadata;
endif
:Build the trend prediction path;
:Generate trend labels and confidence scores;
:Create the future dates;
:Save the prediction record;
:Show the trend forecast to the user;
stop

@enduml
```

## 4.3.4 Price Forecasting Module (LSTM and GRU)

```plantuml
@startuml
title 4.3.4 Price Forecasting Module (LSTM and GRU)

start
:Open price forecasting mode;
:Select the source, range, model, and forecast horizon;
:Load historical prices for the selected source;
:Limit the history to the chosen range;
if (Selected model is LSTM?) then (LSTM)
  :Prepare the sequential input window;
  :Run the LSTM forecast engine;
elseif (Selected model is GRU?) then (GRU)
  :Prepare the sequential input window;
  :Run the GRU forecast engine;
else (fallback)
  :Use the fallback forecasting strategy;
endif
:Classify the forecast path into trend labels and scores;
:Generate the future dates;
:Save the price forecast record;
:Return forecast values and model metadata;
stop

@enduml
```

## 4.3.5 Prediction History Module

```plantuml
@startuml
title 4.3.5 Prediction History Module

start
:Open the history page;
:Load the first page of prediction records;
:Calculate summary counters;
if (User selects a price or trend filter?) then (yes)
  :Filter the records by prediction kind;
endif
if (User loads more records?) then (yes)
  :Fetch the next page of history;
  :Append the new records to the list;
endif
if (User exports CSV?) then (yes)
  :Generate a CSV file for the active filter;
  :Download the file;
endif
if (User opens a record?) then (yes)
  :Display the stored forecast payload;
endif
:Keep the history view synchronized with the current filter;
stop

@enduml
```

## 4.3.6 Administrative Module

```plantuml
@startuml
title 4.3.6 Administrative Module

start
:Open the admin console;
:Verify admin permission;
if (Access granted?) then (yes)
  :Load the admin overview data;
  :Select an admin task;
  switch (Task type)
  case (Manage models)
    :Open model management;
    :Create a new model;
    :Update an existing model;
    :Activate or deactivate a model;
    :Set the default model;
  case (Manage datasets)
    :Open dataset management;
    :Activate or deactivate a dataset;
    :Export the dataset CSV;
  case (Manage users)
    :Open user management;
    :Change user roles;
    :Toggle user activity;
  case (Manage crawler runs)
    :Open crawler management;
    :Submit a crawler task;
    :Monitor crawler progress;
    :Download the crawler report;
  case (Export prediction history)
    :Generate the admin prediction export CSV;
  endswitch
  :Refresh the admin dashboard state;
else (no)
  :Display the access denied message;
endif
stop

@enduml
```

## 4.3.7 News Module

```plantuml
@startuml
title 4.3.7 News Module

start
:Open the news page;
:Load active news categories;
:Load articles for the selected category;
if (Featured-only filter is enabled?) then (yes)
  :Keep featured articles only;
endif
if (User selects an article?) then (yes)
  :Fetch article details by slug;
  :Display the title, summary, image, and source link;
endif
:Render the news list and the detail panel;
stop

@enduml
```

## 4.3.8 AI Assistant Module

```plantuml
@startuml
title 4.3.8 AI Assistant Module

start
:Open the assistant widget;
:Read the latest conversation context;
:Build the question payload;
if (Question is within the gold domain?) then (yes)
  :Send the query to the assistant service;
  if (A domain-specific answer is available?) then (yes)
    :Return the generated answer;
  else (no)
    :Return the fallback answer;
  endif
else (no)
  :Reject the out-of-scope question;
endif
:Append the response to the chat thread;
stop

@enduml
```

## Notes

- The dashboard diagram already includes the market overview flow because the application loads overview data, price charts, sources, models, and news on the same screen.
- The admin diagram covers model management, dataset management, user management, crawler runs, and prediction export because those are grouped under the administrative area in the codebase.